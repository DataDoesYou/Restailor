# Fix: Missing rt_refresh Cookie After Login

## Problem
Users were getting logged out after approximately 1 hour because the `rt_refresh` cookie was not being set during regular login, only during 2FA step2. This prevented the automatic token refresh mechanism from working.

## Root Cause
The `/token` (OAuth2 login) endpoint in `main.py` was only setting the `rt_session` cookie (access token) but not the `rt_refresh` cookie (refresh token). Users without 2FA would never receive a refresh token, causing automatic logout after the access token expired (default: 60 minutes).

## Solution

### Backend Changes (`main.py`)

1. **Fixed `/token` endpoint** (lines ~3408-3440):
   - Added `refresh_token = security_mod.create_refresh_token(uname)` to generate refresh token
   - Changed access token cookie to use `ACCESS_TOKEN_EXPIRE_MINUTES * 60` instead of hardcoded 7 days
   - Added second `set_cookie` call to set `rt_refresh` with 30-day expiration (matches `REFRESH_TOKEN_EXPIRE_DAYS`)
   - Added detailed logging for both cookies

2. **Enhanced `/auth/refresh` endpoint** (lines ~3800-3860):
   - Added logging to track when `rt_refresh` cookie is missing
   - Added logging when cookies are successfully rotated
   - Changed log level from `debug` to `error` for cookie setting failures

### Frontend Changes (`frontend/lib/tokenRefresh.ts`)

Added comprehensive logging to `backgroundRefresh()` function:
- Log when cookies are being sent
- Log the refresh endpoint URL being called
- Log response status and headers
- Log when new cookies should be set by browser

## Token Lifetimes

- **Access Token (`rt_session`)**: 60 minutes (default, configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Refresh Token (`rt_refresh`)**: 30 days (default, configurable via `REFRESH_TOKEN_EXPIRE_DAYS`)
- **Refresh Interval**: 45 minutes (75% of access token lifetime)

## How It Works Now

1. **Login**: User logs in → backend sets both `rt_session` and `rt_refresh` cookies
2. **Token Refresh**: Frontend timer triggers every 45 minutes → calls `/auth/refresh` → backend validates `rt_refresh` cookie → issues new tokens and rotates both cookies
3. **Session Persistence**: As long as browser tab is open and refresh token is valid, user stays logged in indefinitely

## Testing

Run the test script to verify the fix:
```powershell
.\test_refresh_cookie_fix.ps1
```

You should see both cookies present after login.

## Logs to Check

### Backend (successful login with cookies set)
```
INFO login.set_cookie: domain=None, secure=False (for rt_session and rt_refresh)
INFO login.rt_session_set: user=test@example.com, max_age=3600 seconds
INFO login.rt_refresh_set: user=test@example.com, max_age=2592000 seconds (30 days)
INFO login.success: username=test@example.com, user_id=123, path=bearer_direct, needs_2fa=False, has_refresh_token=True
```

### Backend (successful token refresh)
```
INFO auth.refresh: received request, rt_refresh cookie present=True, cookies_count=2
INFO auth.refresh: rotating tokens for user=test@example.com, domain=None, secure=False
INFO auth.refresh.rt_session_set: user=test@example.com, max_age=3600 seconds
INFO auth.refresh.rt_refresh_set: user=test@example.com, max_age=2592000 seconds (30 days)
```

### Frontend Console (token refresh working)
```
[TokenRefresh] ⏰ Timer fired! Starting refresh...
[TokenRefresh] Starting proactive token refresh
[TokenRefresh] Using API base: /api
[TokenRefresh] Calling refresh endpoint: /api/auth/refresh
[TokenRefresh] Refresh response status: 200
[TokenRefresh] ✅ Token refreshed successfully
[TokenRefresh] New cookies should now be set by the browser
[TokenRefresh] ⏰ Next refresh in 2700s (at 8:35:07 AM)
```

## Related Files Modified
- `main.py`: Fixed login endpoint to set refresh token cookie, enhanced logging
- `frontend/lib/tokenRefresh.ts`: Added comprehensive logging for debugging
- `test_refresh_cookie_fix.ps1`: Test script to verify the fix
