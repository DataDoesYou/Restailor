#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Create all Render.com services for Restailor
.DESCRIPTION
    Uses Render API to create PostgreSQL, Redis, API, Worker, and Frontend services
#>

param(
    [switch]$SkipDatabase,
    [switch]$SkipRedis
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Creating Render Services" -ForegroundColor Cyan
Write-Host "=" * 60

# Get Render API key from Doppler
Write-Host "`n📥 Getting Render API key from Doppler..." -ForegroundColor Yellow
$RENDER_API_KEY = doppler secrets get RENDER_API_KEY --plain --project restailor --config prd

if (-not $RENDER_API_KEY) {
    Write-Error "Could not find Render API key in Doppler. Please set RENDER_API_KEY."
}
Write-Host "✓ Got Render API key" -ForegroundColor Green

$headers = @{
    "Authorization" = "Bearer $RENDER_API_KEY"
    "Content-Type" = "application/json"
}

# Get Owner ID
Write-Host "📥 Getting Render owner ID..." -ForegroundColor Yellow
$owners = Invoke-RestMethod -Uri "https://api.render.com/v1/owners" -Headers $headers
$OWNER_ID = $owners[0].owner.id
Write-Host "✓ Owner ID: $OWNER_ID" -ForegroundColor Green

# Track created service IDs
$serviceIds = @{}

# Step 1: Create PostgreSQL Database
if (-not $SkipDatabase) {
    Write-Host "`n📋 Step 1: Creating PostgreSQL Database..." -ForegroundColor Yellow
    
    $pgBody = @{
        type = "postgres"
        name = "restailor-db"
        ownerId = $OWNER_ID
        plan = "starter"
        region = "ohio"
        databaseName = "restailor"
        databaseUser = "postgres"
    } | ConvertTo-Json
    
    try {
        $pgResult = Invoke-RestMethod -Method POST -Uri "https://api.render.com/v1/postgres" `
            -Headers $headers -Body $pgBody
        Write-Host "✓ Created PostgreSQL: $($pgResult.id)" -ForegroundColor Green
        Write-Host "  Connection: $($pgResult.connectionInfo.internalConnectionString)" -ForegroundColor Gray
        $serviceIds["db"] = $pgResult.id
        $DB_CONNECTION_STRING = $pgResult.connectionInfo.internalConnectionString
    } catch {
        Write-Host "⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "   (Database may already exist or API error)" -ForegroundColor Gray
    }
} else {
    Write-Host "`n⏭️  Skipping database creation" -ForegroundColor Gray
}

# Step 2: Create Redis
if (-not $SkipRedis) {
    Write-Host "`n📋 Step 2: Creating Redis..." -ForegroundColor Yellow
    
    $redisBody = @{
        type = "redis"
        name = "restailor-redis"
        ownerId = $OWNER_ID
        plan = "starter"
        region = "ohio"
        maxmemoryPolicy = "allkeys-lru"
    } | ConvertTo-Json
    
    try {
        $redisResult = Invoke-RestMethod -Method POST -Uri "https://api.render.com/v1/redis" `
            -Headers $headers -Body $redisBody
        Write-Host "✓ Created Redis: $($redisResult.id)" -ForegroundColor Green
        Write-Host "  Connection: $($redisResult.connectionInfo.internalConnectionString)" -ForegroundColor Gray
        $serviceIds["redis"] = $redisResult.id
        $REDIS_CONNECTION_STRING = $redisResult.connectionInfo.internalConnectionString
    } catch {
        Write-Host "⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
        Write-Host "   (Redis may already exist or API error)" -ForegroundColor Gray
    }
} else {
    Write-Host "`n⏭️  Skipping Redis creation" -ForegroundColor Gray
}

# Step 3: Create API Web Service
Write-Host "`n📋 Step 3: Creating API Web Service..." -ForegroundColor Yellow

$apiEnvVars = @{
    STRICT_SECRETS = "1"
    COOKIE_SECURE = "1"
    DOPPLER_PROJECT = "restailor"
    DOPPLER_CONFIG = "prd"
    DOPPLER_ENVIRONMENT = "prd"
    WEBAUTHN_RP_ID = "restailor.com"
    WEBAUTHN_RP_NAME = "Restailor"
    WEBAUTHN_ORIGIN = "https://restailor.com"
    BACKEND_BASE_URL = "https://api.restailor.com"
    FRONTEND_URL = "https://restailor.com"
    FRONTEND_REDIRECT_URL = "https://restailor.com"
}

$apiBody = @{
    type = "web_service"
    name = "restailor-api"
    ownerId = $OWNER_ID
    plan = "starter"
    region = "ohio"
    autoDeploy = "yes"
    serviceDetails = @{
        env = "python"
        buildCommand = "curl -Ls --tlsv1.2 --proto =https --retry 3 https://cli.doppler.com/install.sh | bash && pip install poetry && poetry install --only main"
        startCommand = "doppler run -p restailor -c prd -- poetry run uvicorn main:app --host 0.0.0.0 --port `$PORT"
        healthCheckPath = "/healthz"
        envVars = @($apiEnvVars.GetEnumerator() | ForEach-Object {
            @{ key = $_.Key; value = $_.Value }
        })
        repo = "https://github.com/DataDoesYou/Restailor"
        branch = "main"
    }
} | ConvertTo-Json -Depth 10

try {
    $apiResult = Invoke-RestMethod -Method POST -Uri "https://api.render.com/v1/services" `
        -Headers $headers -Body $apiBody
    Write-Host "✓ Created API Service: $($apiResult.id)" -ForegroundColor Green
    Write-Host "  URL: $($apiResult.serviceDetails.url)" -ForegroundColor Gray
    $serviceIds["api"] = $apiResult.id
} catch {
    Write-Host "⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   Response: $($_.ErrorDetails.Message)" -ForegroundColor Gray
}

# Step 4: Create Worker Service
Write-Host "`n📋 Step 4: Creating Worker Service..." -ForegroundColor Yellow

$workerEnvVars = @{
    STRICT_SECRETS = "1"
    DOPPLER_PROJECT = "restailor"
    DOPPLER_CONFIG = "prd"
    DOPPLER_ENVIRONMENT = "prd"
}

$workerBody = @{
    type = "background_worker"
    name = "restailor-worker"
    ownerId = $OWNER_ID
    plan = "starter"
    region = "ohio"
    autoDeploy = "yes"
    serviceDetails = @{
        env = "python"
        buildCommand = "curl -Ls --tlsv1.2 --proto =https --retry 3 https://cli.doppler.com/install.sh | bash && pip install poetry && poetry install --only main"
        startCommand = "doppler run -p restailor -c prd -- poetry run arq worker.WorkerSettings"
        envVars = @($workerEnvVars.GetEnumerator() | ForEach-Object {
            @{ key = $_.Key; value = $_.Value }
        })
        repo = "https://github.com/DataDoesYou/Restailor"
        branch = "main"
    }
} | ConvertTo-Json -Depth 10

try {
    $workerResult = Invoke-RestMethod -Method POST -Uri "https://api.render.com/v1/services" `
        -Headers $headers -Body $workerBody
    Write-Host "✓ Created Worker Service: $($workerResult.id)" -ForegroundColor Green
    $serviceIds["worker"] = $workerResult.id
} catch {
    Write-Host "⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   Response: $($_.ErrorDetails.Message)" -ForegroundColor Gray
}

# Step 5: Create Frontend Service
Write-Host "`n📋 Step 5: Creating Frontend Service..." -ForegroundColor Yellow

$frontendEnvVars = @{
    NODE_ENV = "production"
    INTERNAL_API_BASE_URL = "https://api.restailor.com"
    NEXT_PUBLIC_API_URL = "https://api.restailor.com"
    NEXT_PUBLIC_API_BASE_URL = "https://api.restailor.com"
    NEXT_PUBLIC_SITE_URL = "https://restailor.com"
    NEXT_PUBLIC_FEATURE_ANALYTICS = "1"
    NEXT_TELEMETRY_DISABLED = "1"
}

$frontendBody = @{
    type = "web_service"
    name = "restailor-frontend"
    ownerId = $OWNER_ID
    plan = "starter"
    region = "ohio"
    autoDeploy = "yes"
    serviceDetails = @{
        env = "node"
        buildCommand = "cd frontend && npm install && npm run build"
        startCommand = "cd frontend && npm start"
        envVars = @($frontendEnvVars.GetEnumerator() | ForEach-Object {
            @{ key = $_.Key; value = $_.Value }
        })
        repo = "https://github.com/DataDoesYou/Restailor"
        branch = "main"
    }
} | ConvertTo-Json -Depth 10

try {
    $frontendResult = Invoke-RestMethod -Method POST -Uri "https://api.render.com/v1/services" `
        -Headers $headers -Body $frontendBody
    Write-Host "✓ Created Frontend Service: $($frontendResult.id)" -ForegroundColor Green
    Write-Host "  URL: $($frontendResult.serviceDetails.url)" -ForegroundColor Gray
    $serviceIds["frontend"] = $frontendResult.id
} catch {
    Write-Host "⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "   Response: $($_.ErrorDetails.Message)" -ForegroundColor Gray
}

# Summary
Write-Host "`n" + ("=" * 60)
Write-Host "✅ Service Creation Complete!" -ForegroundColor Green
Write-Host ("=" * 60)

Write-Host "`n📋 Created Services:"
foreach ($service in $serviceIds.GetEnumerator()) {
    Write-Host "  • $($service.Key): $($service.Value)" -ForegroundColor Cyan
}

Write-Host "`n⚠️  Next Steps:" -ForegroundColor Yellow
Write-Host "1. Add secrets to each service (run: .\scripts\sync_doppler_to_render.ps1)"
Write-Host "2. Link DATABASE_URL and REDIS_URL to services"
Write-Host "3. Add custom domains (api.restailor.com, restailor.com)"
Write-Host "4. Configure Cloudflare DNS (run: .\scripts\configure_cloudflare_dns.ps1)"
Write-Host "5. Monitor first deployment in Render Dashboard"

Write-Host "`n🔗 Render Dashboard: https://dashboard.render.com"
Write-Host ""

