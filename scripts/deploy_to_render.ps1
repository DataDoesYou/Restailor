#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Complete Render deployment via Dashboard with CLI verification
.DESCRIPTION
    Guides through Render deployment and verifies with CLI
#>

$ErrorActionPreference = "Stop"

# Ensure Render CLI is in PATH
$env:Path = "$env:LOCALAPPDATA\Programs\Render;$env:Path"

# Verify render command is available
if (-not (Get-Command render -ErrorAction SilentlyContinue)) {
    Write-Error "Render CLI not found. Please ensure it's installed in $env:LOCALAPPDATA\Programs\Render"
}

Write-Host "`n🚀 Render.com Full Deployment" -ForegroundColor Cyan
Write-Host "=" * 70

# Step 1: Verify authentication
Write-Host "`n📋 Step 1: Verifying Render CLI authentication..." -ForegroundColor Yellow
try {
    $whoamiOutput = render whoami --output text 2>&1 | Out-String
    if ($whoamiOutput -match "Name: (.+)") {
        $name = $matches[1].Trim()
        Write-Host "✓ Authenticated as: $name" -ForegroundColor Green
    } else {
        throw "Unable to verify authentication"
    }
} catch {
    Write-Host "❌ Not authenticated. Please run: render login" -ForegroundColor Red
    exit 1
}

# Step 2: Open Blueprint deployment page
Write-Host "`n📋 Step 2: Opening Render Blueprint deployment..." -ForegroundColor Yellow
$blueprintUrl = "https://dashboard.render.com/select-repo?type=blueprint"
Write-Host "Opening: $blueprintUrl" -ForegroundColor Cyan

Start-Process $blueprintUrl

Write-Host "`n📝 In the browser:" -ForegroundColor White
Write-Host "  1. Connect GitHub account (if needed)"
Write-Host "  2. Select: DataDoesYou/Restailor"
Write-Host "  3. Branch: main"
Write-Host "  4. Blueprint file: render.yaml (auto-detected)"
Write-Host "  5. Click 'Apply'"
Write-Host ""

Write-Host "⏳ Waiting for you to create services..." -ForegroundColor Yellow
Write-Host "Press Enter once all services are created and initialized..." -ForegroundColor Cyan
$null = Read-Host

# Step 3: Verify services were created
Write-Host "`n📋 Step 3: Verifying created services..." -ForegroundColor Yellow
$services = render services list --output json | ConvertFrom-Json

if (-not $services -or $services.Count -eq 0) {
    Write-Host "⚠️  No services found. Make sure Blueprint deployment completed." -ForegroundColor Yellow
    Write-Host "Checking again in 5 seconds..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
    $services = render services list --output json | ConvertFrom-Json
}

if ($services -and $services.Count -gt 0) {
    Write-Host "✓ Found $($services.Count) services:" -ForegroundColor Green
    foreach ($svc in $services) {
        $status = if ($svc.suspended -eq "suspended") { "⏸️" } else { "✓" }
        Write-Host "  $status $($svc.name) ($($svc.type))" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ No services found. Please complete Blueprint deployment first." -ForegroundColor Red
    exit 1
}

# Step 4: Get service IDs for later use
$apiService = $services | Where-Object { $_.name -like "*api*" } | Select-Object -First 1
$workerService = $services | Where-Object { $_.name -like "*worker*" } | Select-Object -First 1
$frontendService = $services | Where-Object { $_.name -like "*frontend*" } | Select-Object -First 1
$dbService = $services | Where-Object { $_.type -eq "postgres" } | Select-Object -First 1
$redisService = $services | Where-Object { $_.type -eq "redis" } | Select-Object -First 1

Write-Host "`n📝 Service IDs:" -ForegroundColor Yellow
if ($apiService) { Write-Host "  API: $($apiService.id)" -ForegroundColor Gray }
if ($workerService) { Write-Host "  Worker: $($workerService.id)" -ForegroundColor Gray }
if ($frontendService) { Write-Host "  Frontend: $($frontendService.id)" -ForegroundColor Gray }
if ($dbService) { Write-Host "  Database: $($dbService.id)" -ForegroundColor Gray }
if ($redisService) { Write-Host "  Redis: $($redisService.id)" -ForegroundColor Gray }

# Step 5: Sync secrets from Doppler
Write-Host "`n📋 Step 4: Syncing secrets from Doppler..." -ForegroundColor Yellow
Write-Host "Would you like to sync secrets now? (Y/n): " -ForegroundColor Cyan -NoNewline
$response = Read-Host

if ($response -eq "" -or $response -eq "Y" -or $response -eq "y") {
    if (Test-Path ".\scripts\sync_doppler_to_render.ps1") {
        Write-Host "Running sync script..." -ForegroundColor Gray
        & ".\scripts\sync_doppler_to_render.ps1"
    } else {
        Write-Host "⚠️  Sync script not found. Please manually add secrets in Render Dashboard." -ForegroundColor Yellow
    }
} else {
    Write-Host "⏭️  Skipping secret sync" -ForegroundColor Gray
}

# Step 6: Add custom domains
Write-Host "`n📋 Step 5: Custom Domain Configuration" -ForegroundColor Yellow
Write-Host "DNS records are already configured in Cloudflare:" -ForegroundColor Green
Write-Host "  ✓ api.restailor.com -> restailor-api.onrender.com"
Write-Host "  ✓ restailor.com -> restailor-frontend.onrender.com"  
Write-Host "  ✓ www.restailor.com -> restailor-frontend.onrender.com"

Write-Host "`n📝 Add custom domains in Render Dashboard:" -ForegroundColor White
if ($apiService) {
    Write-Host "  1. API Service: https://dashboard.render.com/web/$($apiService.id)/settings#custom-domains" -ForegroundColor Cyan
    Write-Host "     Add: api.restailor.com"
}
if ($frontendService) {
    Write-Host "  2. Frontend Service: https://dashboard.render.com/web/$($frontendService.id)/settings#custom-domains" -ForegroundColor Cyan
    Write-Host "     Add: restailor.com"
    Write-Host "     Add: www.restailor.com"
}

Write-Host "`nOpen these links now? (Y/n): " -ForegroundColor Yellow -NoNewline
$response = Read-Host

if ($response -eq "" -or $response -eq "Y" -or $response -eq "y") {
    if ($apiService) {
        Start-Process "https://dashboard.render.com/web/$($apiService.id)/settings#custom-domains"
        Start-Sleep -Seconds 1
    }
    if ($frontendService) {
        Start-Process "https://dashboard.render.com/web/$($frontendService.id)/settings#custom-domains"
    }
}

# Summary
Write-Host "`n" + ("=" * 70)
Write-Host "✅ Deployment Setup Complete!" -ForegroundColor Green
Write-Host ("=" * 70)

Write-Host "`n📋 Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Wait for initial deployments to complete (5-10 minutes)"
Write-Host "  2. Add custom domains in Render (if not done)"
Write-Host "  3. Run database migrations on API service:"
Write-Host "     render ssh $($apiService.id)"
Write-Host "     poetry run alembic upgrade head"
Write-Host "  4. Test endpoints:"
Write-Host "     curl https://api.restailor.com/healthz"
Write-Host "     curl https://restailor.com"

Write-Host "`n🔗 Useful Links:" -ForegroundColor Cyan
Write-Host "  Dashboard: https://dashboard.render.com"
Write-Host "  Logs (API): render logs $($apiService.id) --tail"
Write-Host "  Logs (Frontend): render logs $($frontendService.id) --tail"

Write-Host "`n💡 Monitor deployment progress:" -ForegroundColor Yellow
Write-Host "   render deploys list --output json | ConvertFrom-Json | Select-Object -First 5 | Format-Table"

Write-Host ""
