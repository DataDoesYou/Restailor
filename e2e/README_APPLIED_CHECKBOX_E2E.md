# E2E Test: Applied Checkbox Database Update

This test verifies that toggling the Applied checkbox on Resume Tailor page **immediately updates the database**.

## Prerequisites

1. Backend server running (Docker or local)
2. PostgreSQL database accessible
3. Doppler CLI installed and configured

## How to Run

**Option 1: Using Doppler (Recommended)**

```powershell
# Run with Doppler for automatic credential injection
doppler run -- python e2e/applied_checkbox_db_simple_e2e.py
```

**Option 2: Using Poetry + Doppler**

```powershell
doppler run -- poetry run python e2e/applied_checkbox_db_simple_e2e.py
```

**Option 3: Manual Environment Variables (if Doppler unavailable)**

```powershell
$env:BACKEND_URL="http://localhost:5000"
$env:POSTGRES_HOST="localhost"
$env:POSTGRES_PORT="5432"
$env:POSTGRES_DB="restailor"
$env:POSTGRES_USER="your_db_user"
$env:POSTGRES_PASSWORD="your_db_password"

poetry run python e2e/applied_checkbox_db_simple_e2e.py
```

## What It Tests

1. ✅ Creates test user and logs in
2. ✅ Applies a job (POST /applications/jd/apply)
3. ✅ **IMMEDIATELY** queries database to verify `is_applied=true`
4. ✅ Unapplies the job (DELETE /applications/jd/apply)
5. ✅ **IMMEDIATELY** queries database to verify `is_applied=false`
6. ✅ Verifies cascade: `is_interviewing`, `is_offer`, `is_hired` all cleared
7. ✅ Cleans up: Deletes test user and all associated data

## Expected Output

```
Using backend at http://localhost:5000...
Connecting to database at localhost:5432/restailor...
✓ Database connected

1. Creating test user: e2e-applied-abc123@test.local
✓ User created

2. Logging in...
✓ Logged in
✓ User ID: 123

3. Applying a job (POST /applications/jd/apply)...
✓ Applied job (took 45.23ms)
  jdHash: abc123...
  appliedKey: 123:abc123:def456...
  Response isApplied: True

4. Verifying database state IMMEDIATELY after apply...
  Database query took: 2.15ms
  Database is_applied: True
✓ PASS: Database correctly shows is_applied=true

5. Unapplying the job (DELETE /applications/jd/apply)...
✓ Unapplied job (took 42.10ms)
  Response isApplied: False

6. Verifying database state IMMEDIATELY after unapply...
  Database query took: 2.08ms
  Database is_applied: False
  Database is_interviewing: False
  Database is_offer: False
  Database is_hired: False
✓ PASS: Database correctly shows is_applied=false
✓ PASS: All IOH flags cleared (cascade works)

✅ ALL TESTS PASSED!

Summary:
  Apply request: 45.23ms
  Unapply request: 42.10ms
  Database is IMMEDIATELY updated after mutations ✓

7. Cleanup: Deleting test user and data...
✓ Cleaned up test user: e2e-applied-abc123@test.local
  Deleted: 1 analytics, 1 applications, 0 jobs, user_id=123
```

## If Test Fails

The test will show **exactly** what's wrong:

```
❌ FAIL: Database shows is_applied=True, expected False!

🔥 THIS IS THE BUG: Database was NOT updated after DELETE request!
```

This means:
- The DELETE request reached the backend
- Backend returned success
- **BUT** the database row was NOT updated
- This is a transaction/commit issue in the backend

## Manual Database Check

While test is running, you can manually query:

```sql
SELECT id, applied_key, is_applied, is_interviewing, is_offer, is_hired, updated_at
FROM public.applications
WHERE user_id = YOUR_TEST_USER_ID
ORDER BY updated_at DESC
LIMIT 5;
```

Watch the `is_applied` column flip from `true` → `false` in real-time.
