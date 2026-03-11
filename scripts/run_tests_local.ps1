<#!
.SYNOPSIS
  Run backend pytest suite against local Postgres (not SQLite fallback).
.DESCRIPTION
  Ensures required env vars are mapped, runs Alembic migrations, then executes pytest.
  Usage examples:
    doppler run -- pwsh -File scripts/run_tests_local.ps1           # all tests
    doppler run -- pwsh -File scripts/run_tests_local.ps1 tests/test_admin_stepup_and_trusted_devices.py::test_admin_stepup_flow_requires_ticket_and_respects_ttl
.NOTES
  Exits non‑zero on failure. Skips SQLite fallback so 2FA columns & other migrated fields exist.
#>
param(
  [Parameter(Mandatory=$false, Position=0, ValueFromRemainingArguments=$true)]
  [string[]] $PytestArgs,
  [switch] $AutoStartDocker = $true
)

Write-Host "[run-tests] Preparing environment" -ForegroundColor Cyan

# Flag so conftest.py knows we're invoking via the approved script
$env:RUN_TESTS_VIA_SCRIPT = "1"

# Map Doppler/compose style vars to what the app expects if not already set
if (-not $env:DB_USER -and $env:POSTGRES_USER) { $env:DB_USER = $env:POSTGRES_USER }
if (-not $env:DB_NAME -and $env:POSTGRES_DB)   { $env:DB_NAME = $env:POSTGRES_DB }
if (-not $env:DB_HOST) { $env:DB_HOST = "localhost" }
if (-not $env:DB_PORT) { $env:DB_PORT = "5432" }
# If running on host (not inside docker) and host is the docker service name, rewrite
if ($env:DB_HOST -eq 'postgres') { $env:DB_HOST = 'localhost' }
# Ensure password is available under at least one of the checked names
if (-not $env:DB_PASSWORD -and $env:POSTGRES_PASSWORD) { $env:DB_PASSWORD = $env:POSTGRES_PASSWORD }

# Fail fast if critical variables still missing (2FA tests require real schema)
$missing = @()
if (-not $env:DB_USER) { $missing += 'DB_USER or POSTGRES_USER' }
if (-not $env:DB_NAME) { $missing += 'DB_NAME or POSTGRES_DB' }
if (-not $env:DB_PASSWORD) { $missing += 'DB_PASSWORD or POSTGRES_PASSWORD' }
if ($missing.Count -gt 0) {
  Write-Error "Missing required database settings: $($missing -join ', '). Supply via Doppler or env vars."; exit 2
}

# Disable test-mode fallback so we exercise real schema
$env:TEST_MODE = "0"
# Relax strict secret enforcement during local test runs
if (-not $env:STRICT_SECRETS) { $env:STRICT_SECRETS = "0" }
# Provide a deterministic PII key if Doppler doesn't supply one
if (-not $env:PII_ENCRYPTION_KEY) { $env:PII_ENCRYPTION_KEY = "local_test_pii_key" }

# Basic sanity output (mask password length only)
$maskedPw = if ($env:DB_PASSWORD) { ("*" * ($env:DB_PASSWORD.Length)) } else { "<missing>" }
Write-Host "[run-tests] DB: $($env:DB_USER)@$($env:DB_HOST):$($env:DB_PORT)/$($env:DB_NAME) pw=$maskedPw" -ForegroundColor DarkGray

# Force DATABASE_URL for Alembic & application imports (override any earlier fallback)
$env:DATABASE_URL = "postgresql://$($env:DB_USER):$($env:DB_PASSWORD)@$($env:DB_HOST):$($env:DB_PORT)/$($env:DB_NAME)"

# Wait for TCP port to be reachable (helpful when docker just started)
$attempt = 0; $maxAttempts = 40
# Force IPv4 for localhost to avoid occasional IPv6 (::1) stalls on some Windows setups
$dbHostForProbe = if ($env:DB_HOST -eq 'localhost') { '127.0.0.1' } else { $env:DB_HOST }
while ($attempt -lt $maxAttempts) {
  $attempt++
  $delay = if ($attempt -lt 10) { 1 } elseif ($attempt -lt 20) { 2 } else { 3 }
  $connected = $false
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($dbHostForProbe, [int]$env:DB_PORT, $null, $null)
    if ($iar.AsyncWaitHandle.WaitOne(1200)) {
      $client.EndConnect($iar); $connected = $true
    }
    $client.Close()
  } catch { }
  if ($connected) { break }

  # After a few quick attempts, optionally auto-start docker postgres
  if ($attempt -eq 5 -and $AutoStartDocker) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
      if (Test-Path 'docker/docker-compose.dev.yml') {
        Write-Host "[run-tests] Attempting to start postgres via docker compose" -ForegroundColor Yellow
        try { docker compose -f docker/docker-compose.dev.yml up -d postgres | Out-Null } catch { }
      }
    }
  }

  Start-Sleep -Seconds $delay
  if ($attempt -eq $maxAttempts) { Write-Error ("Database at {0}:{1} not reachable after ~{2} attempts. Start Docker (postgres) or set DB_* env vars." -f $dbHostForProbe, $env:DB_PORT, $attempt); exit 3 }
}
if ($attempt -gt 1) { Write-Host "[run-tests] DB became reachable after $attempt attempt(s)" -ForegroundColor DarkGray }

# Run migrations (idempotent)
Write-Host "[run-tests] Running Alembic migrations" -ForegroundColor Cyan
poetry run alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Error "Alembic migration failed"; exit $LASTEXITCODE }

# Run pytest (verbose, show progress). If user passed their own -q/-vv we respect their args.
$baseArgs = @('pytest','tests')
$hasVerbosity = $false
foreach ($a in $PytestArgs) { if ($a -match '^-q$' -or $a -match '^-v' ) { $hasVerbosity = $true; break } }
if (-not $hasVerbosity) { $baseArgs += '-vv' }

# If filtering by marker and no tests collected, surface a helpful hint by doing a collect-only dry run after.
Write-Host "[run-tests] Executing: poetry run $($baseArgs + $PytestArgs -join ' ')" -ForegroundColor Cyan
$pytestFull = $baseArgs + $PytestArgs
poetry run @pytestFull
$code = $LASTEXITCODE
if ($code -eq 5) { # pytest exit code 5 = no tests collected
  Write-Warning "No tests collected. Performing --collect-only diagnostic.";
  poetry run pytest --collect-only @PytestArgs | Select-String -Pattern '::' -Context 0,0 | ForEach-Object { $_.Line } | Select-Object -First 50
  Write-Host "Hint: ensure markers/paths are correct. Example: -m requires_pg tests/" -ForegroundColor Yellow
}
exit $code
