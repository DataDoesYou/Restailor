# Logout Timing Investigation

## Findings

### Overview
Users were experiencing "logout" after 1 hour (access token expiry) or unpredictably due to frontend heuristics failing to attempt a token refresh.

### Token Timings
The system uses a dual-token architecture (Access + Refresh):
-   **Access Token (`rt_session`)**: Expires in **60 minutes**. This is a short-lived stateless JWT.
-   **Refresh Token (`rt_refresh`)**: Expires in **30 days**. This is a long-lived stateless JWT.
-   **Refresh Cookie**: `rt_refresh` is long-lived (persistent) to support automatic refresh across browser restarts.

### Root Cause of "Logout after X hours"
The frontend logic relies on a heuristic to determine if a user is "logged in" before attempting network requests.
1.  **Strict Heuristic**: The heuristic (`likelyAuthenticated`) relied on a `localStorage` flag or visible cookies.
    -   `rt_session` and `rt_refresh` are `HttpOnly` cookies, so JavaScript **cannot** see them.
    -   The `localStorage` backup flag (`__rt_auth_expect_true`) expired after **5 minutes**.
2.  **The 1-Hour Bug**:
    -   If a user returns to the app after > 1 hour, the Access Token is expired.
    -   The `localStorage` flag is also expired.
    -   The frontend calls `/users/me` (auth probe).
    -   The backend returns **401 Unauthorized** (because Access Token is expired/missing).
    -   The frontend logic checked `if (wasLogged) tryRefresh()`.
    -   Since the heuristic failed (wasLogged = false), the frontend **did NOT attempt to refresh**.
    -   Result: The user is treated as anonymous/logged out, effectively logging them out after 1 hour of inactivity if they reload or open a new tab.

### Fix Implementation
We have applied fixes in `frontend/lib/api.ts` and `frontend/lib/tokenRefresh.ts`:
1.  **Retry on 401**: The API client now attempts to refresh the token on a 401 error from `/users/me`, *even if* the frontend doesn't think the user is logged in. This allows the HttpOnly `rt_refresh` cookie to be used.
2.  **Extended Heuristic**: The `localStorage` flag (`__rt_auth_expect_true`) now remains considered valid for **30 days** (matching the refresh token lifetime), instead of 5 minutes.
3.  **Heuristic Maintenance**: The `localStorage` flag is now refreshed (timestamp updated) on every successful `/users/me` call, ensuring active users stay "logged in" in the heuristic.

### Expected Behavior After Fix
-   **Active Session**: Stays logged in indefinitely (auto-refreshed every 45 mins while tab is open).
-   **Inactive (Tab Closed) < 30 Days**:
    -   User opens app.
    -   Access Token might be expired.
    -   Frontend probes `/users/me` -> 401.
    -   Frontend catches 401 -> calls `/auth/refresh`.
    -   Backend sees valid `rt_refresh` cookie -> issues new tokens.
    -   Frontend retries `/users/me` -> 200 OK.
    -   User is logged in transparently.
-   **Inactive > 30 Days**:
    -   Refresh token expires.
    -   Frontend refresh attempt fails (401).
    -   User is logged out.
