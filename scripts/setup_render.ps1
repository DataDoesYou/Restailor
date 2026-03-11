#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Automated Render.com deployment setup for Restailor
.DESCRIPTION
    This script automates:
    - Render CLI installation verification
    - Service creation on Render
    - Cloudflare DNS configuration
    - Secret synchronization from Doppler
.NOTES
    Prerequisites: Doppler CLI, Render account, Cloudflare account
#>

param(
    [switch]$SkipRenderSetup,
    [switch]$SkipCloudflare,
    [switch]$SkipSecrets,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Configuration
$PROJECT = "restailor"
$DOPPLER_CONFIG = "prd"
$DOMAIN = "restailor.com"
$REGION = "ohio"

Write-Host "🚀 Restailor - Render.com Deployment Setup" -ForegroundColor Cyan
Write-Host "=" * 60

# Step 1: Verify Prerequisites
Write-Host "`n📋 Step 1: Verifying Prerequisites..." -ForegroundColor Yellow

function Test-Command {
    param($CommandName)
    $null -ne (Get-Command $CommandName -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "doppler")) {
    Write-Error "Doppler CLI not found. Install from: https://docs.doppler.com/docs/install-cli"
}
Write-Host "✓ Doppler CLI found" -ForegroundColor Green

if (-not (Test-Command "render")) {
    Write-Host "⚠️  Render CLI not found. Attempting to install..." -ForegroundColor Yellow
    
    # Try npm installation
    if (Test-Command "npm") {
        npm install -g @render-cli/cli
    } else {
        Write-Error "Render CLI not found and npm not available. Install manually: https://render.com/docs/cli"
    }
}
Write-Host "✓ Render CLI found" -ForegroundColor Green

# Verify authentication
Write-Host "`nVerifying Render authentication..."
try {
    $renderUser = render whoami 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠️  Not logged into Render. Please run: render login" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✓ Authenticated with Render" -ForegroundColor Green
} catch {
    Write-Error "Failed to verify Render authentication. Run: render login"
}

# Step 2: Get Secrets from Doppler
Write-Host "`n📋 Step 2: Loading secrets from Doppler..." -ForegroundColor Yellow

$secretsJson = doppler secrets download --project $PROJECT --config $DOPPLER_CONFIG --format json --no-file
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to fetch secrets from Doppler"
}
$secrets = $secretsJson | ConvertFrom-Json
Write-Host "✓ Loaded $($secrets.PSObject.Properties.Count) secrets from Doppler" -ForegroundColor Green

# Verify required secrets
$requiredSecrets = @(
    "AUTH_SECRET_KEY",
    "PII_ENCRYPTION_KEY",
    "TOTP_FERNET_KEY",
    "SECURITY_REMEMBER_SIGNER_SECRET",
    "CLOUDFLARE_API_TOKEN"
)

foreach ($secret in $requiredSecrets) {
    if (-not $secrets.$secret) {
        Write-Error "Required secret '$secret' not found in Doppler config"
    }
}
Write-Host "✓ All required secrets present" -ForegroundColor Green

# Step 3: Create Render Services
if (-not $SkipRenderSetup) {
    Write-Host "`n📋 Step 3: Setting up Render services..." -ForegroundColor Yellow
    
    if ($DryRun) {
        Write-Host "[DRY RUN] Would create Render services" -ForegroundColor Gray
    } else {
        Write-Host "`nAttempting to use render.yaml blueprint..."
        
        # Check if render.yaml exists
        if (Test-Path "render.yaml") {
            Write-Host "Found render.yaml, launching blueprint..."
            
            # Note: The actual command depends on Render CLI version
            # Some versions use 'blueprint launch', others may differ
            Write-Host "`n⚠️  Manual Step Required:" -ForegroundColor Yellow
            Write-Host "Go to Render Dashboard: https://dashboard.render.com/select-repo?type=blueprint"
            Write-Host "1. Select repository: DataDoesYou/Restailor"
            Write-Host "2. Branch: main"
            Write-Host "3. Blueprint file: render.yaml"
            Write-Host "4. Click 'Apply'"
            Write-Host "`nPress any key once services are created..."
            $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        } else {
            Write-Error "render.yaml not found. Please run from project root."
        }
    }
} else {
    Write-Host "`n⏭️  Skipping Render setup" -ForegroundColor Gray
}

# Step 4: Configure Cloudflare DNS
if (-not $SkipCloudflare) {
    Write-Host "`n📋 Step 4: Configuring Cloudflare DNS..." -ForegroundColor Yellow
    
    $CF_TOKEN = $secrets.CLOUDFLARE_API_TOKEN
    
    if ($DryRun) {
        Write-Host "[DRY RUN] Would configure Cloudflare DNS" -ForegroundColor Gray
    } else {
        # Get Zone ID
        Write-Host "Getting Cloudflare Zone ID for $DOMAIN..."
        $zoneResponse = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones?name=$DOMAIN" `
            -Headers @{ "Authorization" = "Bearer $CF_TOKEN" }
        
        if (-not $zoneResponse.success -or $zoneResponse.result.Count -eq 0) {
            Write-Error "Failed to find Cloudflare zone for $DOMAIN"
        }
        
        $zoneId = $zoneResponse.result[0].id
        Write-Host "✓ Zone ID: $zoneId" -ForegroundColor Green
        
        # Create DNS records
        $dnsRecords = @(
            @{
                type = "CNAME"
                name = "api"
                content = "restailor-api.onrender.com"
                proxied = $true
                ttl = 1
            },
            @{
                type = "CNAME"
                name = "www"
                content = "restailor-frontend.onrender.com"
                proxied = $true
                ttl = 1
            },
            @{
                type = "CNAME"
                name = "@"
                content = "restailor-frontend.onrender.com"
                proxied = $true
                ttl = 1
            }
        )
        
        foreach ($record in $dnsRecords) {
            Write-Host "Creating DNS record: $($record.name).$DOMAIN -> $($record.content)"
            
            try {
                $result = Invoke-RestMethod -Method POST `
                    -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/dns_records" `
                    -Headers @{ 
                        "Authorization" = "Bearer $CF_TOKEN"
                        "Content-Type" = "application/json"
                    } `
                    -Body ($record | ConvertTo-Json)
                
                if ($result.success) {
                    Write-Host "  ✓ Created $($record.name)" -ForegroundColor Green
                } else {
                    Write-Host "  ⚠️  $($result.errors[0].message)" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "  ⚠️  Error: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
        
        # Configure SSL
        Write-Host "`nConfiguring SSL/TLS settings..."
        $sslResult = Invoke-RestMethod -Method PATCH `
            -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/settings/ssl" `
            -Headers @{ 
                "Authorization" = "Bearer $CF_TOKEN"
                "Content-Type" = "application/json"
            } `
            -Body (@{ value = "full" } | ConvertTo-Json)
        
        if ($sslResult.success) {
            Write-Host "✓ SSL set to Full" -ForegroundColor Green
        }
        
        # Enable Always Use HTTPS
        $httpsResult = Invoke-RestMethod -Method PATCH `
            -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/settings/always_use_https" `
            -Headers @{ 
                "Authorization" = "Bearer $CF_TOKEN"
                "Content-Type" = "application/json"
            } `
            -Body (@{ value = "on" } | ConvertTo-Json)
        
        if ($httpsResult.success) {
            Write-Host "✓ Always Use HTTPS enabled" -ForegroundColor Green
        }
    }
} else {
    Write-Host "`n⏭️  Skipping Cloudflare configuration" -ForegroundColor Gray
}

# Step 5: Sync Secrets to Render
if (-not $SkipSecrets) {
    Write-Host "`n📋 Step 5: Syncing secrets to Render services..." -ForegroundColor Yellow
    
    if ($DryRun) {
        Write-Host "[DRY RUN] Would sync secrets to Render" -ForegroundColor Gray
    } else {
        Write-Host "`n⚠️  Manual Step Required:" -ForegroundColor Yellow
        Write-Host "Due to Render CLI limitations, secrets must be set via Dashboard or API"
        Write-Host "`n1. Go to: https://dashboard.render.com"
        Write-Host "2. Select each service (API, Worker, Frontend)"
        Write-Host "3. Go to Environment tab"
        Write-Host "4. Add the following secrets from Doppler:"
        Write-Host ""
        
        $secretsToSync = @{
            "API & Worker" = @(
                "AUTH_SECRET_KEY",
                "VERIFY_SECRET_KEY",
                "RESET_SECRET_KEY",
                "PII_ENCRYPTION_KEY",
                "TOTP_FERNET_KEY",
                "SECURITY_REMEMBER_SIGNER_SECRET",
                "OPENAI_API_KEY",
                "CLAUDE_API_KEY",
                "GEMINI_API_KEY",
                "GROK_API_KEY",
                "STRIPE_SECRET_KEY",
                "STRIPE_PUBLISHABLE_KEY",
                "STRIPE_WEBHOOK_SECRET",
                "TURNSTILE_SECRET_KEY",
                "MAIL_USERNAME",
                "MAIL_PASSWORD"
            )
            "Frontend" = @(
                "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
                "NEXT_PUBLIC_TURNSTILE_SITE_KEY"
            )
        }
        
        foreach ($service in $secretsToSync.Keys) {
            Write-Host "`n$service Service:" -ForegroundColor Cyan
            foreach ($key in $secretsToSync[$service]) {
                $value = $secrets.$key
                if ($key -eq "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY") {
                    $value = $secrets.STRIPE_PUBLISHABLE_KEY
                }
                if ($value) {
                    Write-Host "  • $key = $($value.Substring(0, [Math]::Min(10, $value.Length)))..." -ForegroundColor Gray
                }
            }
        }
        
        Write-Host "`n💡 Tip: Use Doppler's Render integration for automatic sync:" -ForegroundColor Yellow
        Write-Host "   https://docs.doppler.com/docs/render"
    }
} else {
    Write-Host "`n⏭️  Skipping secrets sync" -ForegroundColor Gray
}

# Summary
Write-Host "`n" + ("=" * 60)
Write-Host "✅ Setup Complete!" -ForegroundColor Green
Write-Host ("=" * 60)

Write-Host "`n📋 Next Steps:"
Write-Host "1. Verify DNS propagation: nslookup api.$DOMAIN"
Write-Host "2. Test API health: https://api.$DOMAIN/healthz"
Write-Host "3. Test frontend: https://$DOMAIN"
Write-Host "4. Run database migrations on API service"
Write-Host "5. Monitor deployment logs in Render Dashboard"

Write-Host "`n🔗 Useful Links:"
Write-Host "• Render Dashboard: https://dashboard.render.com"
Write-Host "• Cloudflare Dashboard: https://dash.cloudflare.com"
Write-Host "• Doppler Dashboard: https://dashboard.doppler.com/workplace/$PROJECT/config/$DOPPLER_CONFIG"

Write-Host "`n💡 View logs:"
Write-Host "   render logs <service-id> --tail"

Write-Host "`n📚 Full documentation: docs/RENDER_SETUP.md"
Write-Host ""

