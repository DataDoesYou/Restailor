# Quick test to diagnose pending_2fa token handling against a caller-specified backend.

param(
    [string]$BaseUrl = "http://localhost:8000"
)

$BaseUrl = $BaseUrl.TrimEnd('/')
$TokenUrl = "$BaseUrl/token"
$OptionsUrl = "$BaseUrl/webauthn/authenticate/options"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "WebAuthn Token Diagnostic Test" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "Target: $BaseUrl" -ForegroundColor Yellow
Write-Host ""

# Get credentials
$email = Read-Host "Enter email"
$password = Read-Host "Enter password" -AsSecureString
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))

Write-Host ""
Write-Host "Step 1: Logging in to get pending_2fa token..." -ForegroundColor Yellow

try {
    $headers = @{'Content-Type'='application/x-www-form-urlencoded'}
    $body = "username=$email&password=$passwordPlain"
    $response = Invoke-WebRequest -Uri $TokenUrl -Method POST -Headers $headers -Body $body -UseBasicParsing
    $json = $response.Content | ConvertFrom-Json
    
    Write-Host "✓ Login successful" -ForegroundColor Green
    Write-Host "  Token type: $($json.token_type)" -ForegroundColor Gray
    Write-Host "  Token length: $($json.access_token.Length)" -ForegroundColor Gray
    
    if ($json.token_type -ne "pending_2fa") {
        Write-Host ""
        Write-Host "⚠️  This account doesn't require 2FA. Token type: $($json.token_type)" -ForegroundColor Yellow
        Write-Host "You need an account with WebAuthn/TOTP enabled to test this issue." -ForegroundColor Yellow
        exit
    }
    
    $token = $json.access_token
    
    Write-Host ""
    Write-Host "Step 2: Token received; continuing with direct backend validation..." -ForegroundColor Yellow
    
    Write-Host ""
    Write-Host "Step 3: Testing token against /webauthn/authenticate/options..." -ForegroundColor Yellow
    
    $authHeaders = @{
        'Authorization' = "Bearer $token"
        'Content-Type' = 'application/json'
    }
    
    try {
        $optionsResponse = Invoke-WebRequest -Uri $OptionsUrl `
            -Method POST `
            -Headers $authHeaders `
            -Body '{}' `
            -UseBasicParsing
        
        Write-Host "✓ SUCCESS! Token is valid." -ForegroundColor Green
        Write-Host "  Status: $($optionsResponse.StatusCode)" -ForegroundColor Gray
        Write-Host ""
        Write-Host "🤔 Interesting - token works via API but fails in browser!" -ForegroundColor Yellow
        Write-Host "This suggests a frontend issue (token corruption/modification)." -ForegroundColor Yellow
        
    } catch {
        Write-Host "✗ FAILED with status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
        
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $errorBody = $reader.ReadToEnd()
            $errorJson = $errorBody | ConvertFrom-Json
            
            Write-Host "  Error detail: $($errorJson.detail)" -ForegroundColor Red
            Write-Host ""
            
            if ($errorJson.detail -eq "invalid_pending_token" -or $errorJson.detail -eq "missing_pending_token") {
                Write-Host "🔍 ROOT CAUSE IDENTIFIED:" -ForegroundColor Cyan
                Write-Host ""
                Write-Host "The pending_2fa token is being rejected by the backend." -ForegroundColor Yellow
                Write-Host "Since the token was JUST issued, this indicates:" -ForegroundColor Yellow
                Write-Host ""
                Write-Host "Most likely causes:" -ForegroundColor White
                Write-Host "  1. ⏰ CLOCK SKEW - Server time is ahead, token appears expired" -ForegroundColor Yellow
                Write-Host "  2. 🔑 Different SECRET_KEY between servers (if multiple instances)" -ForegroundColor Yellow
                Write-Host "  3. 🔐 Token signature validation failing" -ForegroundColor Yellow
                Write-Host ""
                Write-Host "Check the decoded token above for expiration time!" -ForegroundColor Cyan
            }
            
        } catch {
            Write-Host "  Could not parse error response" -ForegroundColor Gray
        }
    }
    
} catch {
    Write-Host "✗ Login failed: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        try {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $errorBody = $reader.ReadToEnd()
            Write-Host "  Response: $errorBody" -ForegroundColor Gray
        } catch {}
    }
}

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
