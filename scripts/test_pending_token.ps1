# Test script to verify a pending_2fa token against a caller-specified backend.

param(
    [Parameter(Mandatory=$true)]
    [string]$Token,

    [string]$BaseUrl = "http://localhost:8000"
)

$BaseUrl = $BaseUrl.TrimEnd('/')
$OptionsUrl = "$BaseUrl/webauthn/authenticate/options"

Write-Host "Testing pending_2fa token..." -ForegroundColor Cyan
Write-Host "Target: $BaseUrl" -ForegroundColor Yellow
Write-Host "Token length: $($Token.Length)" -ForegroundColor Yellow
Write-Host "First 20 chars: $($Token.Substring(0, [Math]::Min(20, $Token.Length)))" -ForegroundColor Yellow
Write-Host ""

# Test 1: Try to use the token immediately
Write-Host "Test 1: Calling /webauthn/authenticate/options with token..." -ForegroundColor Cyan
try {
    $headers = @{
        'Authorization' = "Bearer $Token"
        'Content-Type' = 'application/json'
    }
    
    $response = Invoke-WebRequest -Uri $OptionsUrl `
        -Method POST `
        -Headers $headers `
        -Body '{}' `
        -UseBasicParsing
    
    Write-Host "✓ SUCCESS! Status: $($response.StatusCode)" -ForegroundColor Green
    Write-Host "Response: $($response.Content)" -ForegroundColor Green
} catch {
    Write-Host "✗ FAILED! Status: $($_.Exception.Response.StatusCode.value__)" -ForegroundColor Red
    $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
    $responseBody = $reader.ReadToEnd()
    Write-Host "Error: $responseBody" -ForegroundColor Red
    
    # Parse the error
    try {
        $errorJson = $responseBody | ConvertFrom-Json
        Write-Host ""
        Write-Host "Error detail: $($errorJson.detail)" -ForegroundColor Yellow
        
        if ($errorJson.detail -eq "invalid_pending_token") {
            Write-Host ""
            Write-Host "DIAGNOSIS: Token is being rejected as invalid" -ForegroundColor Red
            Write-Host "Possible causes:" -ForegroundColor Yellow
            Write-Host "  1. Clock skew - server time is ahead/behind" -ForegroundColor Yellow
            Write-Host "  2. Wrong SECRET_KEY in production" -ForegroundColor Yellow
            Write-Host "  3. Token was modified/corrupted in transit" -ForegroundColor Yellow
            Write-Host "  4. Token scope is wrong (should be 'pending_2fa')" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Could not parse error response" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Test 2: Decode token locally (requires PyJWT)..." -ForegroundColor Cyan
Write-Host "Run this Python to decode (without verifying signature):" -ForegroundColor Yellow
Write-Host @"
import jwt
import json
token = "$Token"
decoded = jwt.decode(token, options={"verify_signature": False})
print(json.dumps(decoded, indent=2))
"@ -ForegroundColor Gray
