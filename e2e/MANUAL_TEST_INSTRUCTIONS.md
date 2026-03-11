# Manual Test: Applied Checkbox Database Update

Since the automated E2E test requires correct backend configuration, here's a simple **manual test** you can run right now:

## Test Steps

### 1. Open Three Windows:

1. **Browser** - Your Resume Tailor app
2. **Database Client** - Azure Data Studio / pgAdmin / psql
3. **Browser DevTools Console** - F12 → Console tab

### 2. Prepare SQL Query

In your database client, prepare this query (don't run yet):

```sql
SELECT 
    id,
    applied_key,
    is_applied,
    is_interviewing,
    is_offer,
    is_hired,
    updated_at
FROM public.applications
WHERE user_id = YOUR_USER_ID  -- Replace with your actual user ID
ORDER BY updated_at DESC
LIMIT 1;
```

### 3. Test Unapply Flow

1. **Go to History page** → Find an **Applied** job → Click to open on Resume Tailor page
2. **Verify checkbox is checked** ✅
3. **Open DevTools Console** - Watch for log messages
4. **Uncheck the Applied checkbox**
5. **Watch the console logs**:
   ```
   [UNAPPLY] Starting DELETE request { jdHash: "..." }
   [UNAPPLY] DELETE completed { duration: "45.23ms", success: true, dbIsApplied: false, ... }
   ```
6. **IMMEDIATELY run the SQL query** (within 1-2 seconds)
7. **Check the result**:
   - `is_applied` should be `false` (or 0)
   - `is_interviewing` should be `false` (cascade)
   - `is_offer` should be `false` (cascade)
   - `is_hired` should be `false` (cascade)

### 4. Test Apply Flow

1. **Check the Applied checkbox again**
2. **Watch the console logs**:
   ```
   [APPLY] Sending POST /applications/jd/apply ...
   [APPLY] Response received { ok: true, dbIsApplied: true, ... }
   ```
3. **IMMEDIATELY run the SQL query again**
4. **Check the result**:
   - `is_applied` should be `true` (or 1)

## Expected Behavior

✅ **PASS**: Database shows correct state immediately after console logs "completed"
❌ **FAIL**: Database still shows old state even after logs show "completed"

## If Test Fails

The console logs will tell you exactly what's wrong:

### Console shows DELETE completed but database unchanged:
```
[UNAPPLY] DELETE completed { duration: "45.23ms", success: true, dbIsApplied: false, matches: true }
```
**But SQL shows `is_applied = true`**

This means:
- Frontend sent DELETE request ✅
- Backend received DELETE request ✅
- Backend returned success ✅
- **Backend response claims `isApplied=false`** ✅
- **But database wasn't actually updated** ❌

**Root cause**: Backend transaction issue (commit not happening)

### Console shows mismatch warning:
```
❌ FAIL: Database shows is_applied=True, expected False!
🔥 THIS IS THE BUG: Database was NOT updated after DELETE request!
```

This means the backend logging we added will show exactly what's happening in the transaction.

## Check Backend Logs

Look for these logs in your backend (Docker logs or terminal):

```
[UNAPPLY] Starting DELETE for jdHash=abc123... appliedKey=4:abc123:def456... BEFORE: is_applied=True
[UNAPPLY] UPDATE executed
[UNAPPLY] Flushed to database
[UNAPPLY] Transaction committed
[UNAPPLY] Refreshed from DB, AFTER: is_applied=False, returning isApplied=False
```

If you see all these logs but database still shows `is_applied=true`, then we have a **database connection pooling** or **transaction isolation** issue.

## Alternative: Use Backend Logs Only

If you don't want to run SQL queries manually, just watch the backend logs:

1. Uncheck Applied checkbox
2. Check backend logs for `[UNAPPLY]` messages
3. Look for `AFTER: is_applied=False` in the logs
4. If backend logs show `is_applied=False` but your UI/History page shows it as still Applied when you navigate back, then the database update didn't persist

---

**This manual test will definitively show if the database is being updated immediately!** 🎯
