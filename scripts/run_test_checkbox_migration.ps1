# Test DB Checkbox Migration Script
# Run this to apply the test_checkbox table migration

Write-Host "Running test_checkbox migration..." -ForegroundColor Cyan

try {
    # Run the migration
    doppler run -- alembic upgrade head
    
    Write-Host "`nMigration completed successfully!" -ForegroundColor Green
    Write-Host "`nYou can now access the DB Test page at: http://localhost:3000/db-test" -ForegroundColor Yellow
    Write-Host "(Make sure you're logged in first)" -ForegroundColor Gray
    
} catch {
    Write-Host "`nMigration failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
