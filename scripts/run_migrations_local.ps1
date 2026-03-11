<#!
.SYNOPSIS
  Run Alembic migrations locally using Doppler-provided (or manually set) env vars.
.DESCRIPTION
  Mirrors environment prep logic from run_tests_local.ps1 but only performs schema upgrade.
  Useful for: doppler run -- pwsh -File scripts/run_migrations_local.ps1
.PARAMETER AutoStartDocker
  Attempt to start the postgres service from docker-compose.dev.yml if not reachable.
.EXAMPLE
  doppler run -- pwsh -File scripts/run_migrations_local.ps1
  doppler run -- pwsh -File scripts/run_migrations_local.ps1 -AutoStartDocker:$false
.NOTES
  Exits non‑zero on failure. Does NOT run tests.
#>
param(
  [switch] $AutoStartDocker
)

Write-Host "[migrations] Preparing environment" -ForegroundColor Cyan

# Map common docker-compose vars -> app vars if missing
if (-not $env:DB_USER -and $env:POSTGRES_USER) { $env:DB_USER = $env:POSTGRES_USER }
if (-not $env:DB_NAME -and $env:POSTGRES_DB)   { $env:DB_NAME = $env:POSTGRES_DB }
if (-not $env:DB_HOST) { $env:DB_HOST = "localhost" }
if (-not $env:DB_PORT) { $env:DB_PORT = "5432" }
if ($env:DB_HOST -eq 'postgres') { $env:DB_HOST = 'localhost' }
if (-not $env:DB_PASSWORD -and $env:POSTGRES_PASSWORD) { $env:DB_PASSWORD = $env:POSTGRES_PASSWORD }

# Required settings
$missing = @()
if (-not $env:DB_USER) { $missing += 'DB_USER or POSTGRES_USER' }
if (-not $env:DB_NAME) { $missing += 'DB_NAME or POSTGRES_DB' }
if (-not $env:DB_PASSWORD) { $missing += 'DB_PASSWORD or POSTGRES_PASSWORD' }
if ($missing.Count -gt 0) { Write-Error "Missing required database settings: $($missing -join ', ')."; exit 2 }

# Ensure fallback flags for full schema (no SQLite fallback)
$env:TEST_MODE = "0"
if (-not $env:STRICT_SECRETS) { $env:STRICT_SECRETS = "0" }
if (-not $env:PII_ENCRYPTION_KEY) { $env:PII_ENCRYPTION_KEY = "local_migration_pii_key" }

# Log (mask password)
$maskedPw = if ($env:DB_PASSWORD) { ("*" * ($env:DB_PASSWORD.Length)) } else { "<missing>" }
Write-Host "[migrations] DB: $($env:DB_USER)@$($env:DB_HOST):$($env:DB_PORT)/$($env:DB_NAME) pw=$maskedPw" -ForegroundColor DarkGray

# Wait for DB to accept TCP connections
$attempt = 0; $maxAttempts = 40
$dbHostForProbe = if ($env:DB_HOST -eq 'localhost') { '127.0.0.1' } else { $env:DB_HOST }
while ($attempt -lt $maxAttempts) {
  $attempt++
  $delay = if ($attempt -lt 10) { 1 } elseif ($attempt -lt 20) { 2 } else { 3 }
  $connected = $false
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($dbHostForProbe, [int]$env:DB_PORT, $null, $null)
    if ($iar.AsyncWaitHandle.WaitOne(1200)) { $client.EndConnect($iar); $connected = $true }
    $client.Close()
  } catch { }
  if ($connected) { break }
  if ($attempt -eq 5 -and $AutoStartDocker) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
      if (Test-Path 'docker/docker-compose.dev.yml') {
        Write-Host "[migrations] Attempting to start postgres via docker compose" -ForegroundColor Yellow
        try { docker compose -f docker/docker-compose.dev.yml up -d postgres | Out-Null } catch { }
      }
    }
  }
  Start-Sleep -Seconds $delay
  if ($attempt -eq $maxAttempts) { Write-Error ("Database at {0}:{1} not reachable after ~{2} attempts." -f $dbHostForProbe, $env:DB_PORT, $attempt); exit 3 }
}
if ($attempt -gt 1) { Write-Host "[migrations] DB reachable after $attempt attempt(s)" -ForegroundColor DarkGray }

# Run migrations
Write-Host "[migrations] Running Alembic upgrade head" -ForegroundColor Cyan
poetry run alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Error "Alembic migration failed"; exit $LASTEXITCODE }

Write-Host "[migrations] Success" -ForegroundColor Green
