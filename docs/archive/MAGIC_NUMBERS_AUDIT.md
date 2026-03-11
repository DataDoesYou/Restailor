# Magic Numbers Audit Report

**Branch:** `refactor/check-magic-numbers`  
**Date:** November 1, 2025  
**Status:** Analysis Complete

## Overview

This document catalogs all magic numbers found in the codebase. Magic numbers are numeric literals that appear in code without clear semantic meaning. They should ideally be replaced with named constants.

---

## Priority Categories

### 🔴 HIGH PRIORITY - Security & Configuration

#### Authentication & Token Expiration
**File:** `restailor/security.py`
- **Line 61:** `60` - Default access token expiration (minutes)
  ```python
  ACCESS_TOKEN_EXPIRE_MINUTES = _int_env_or_cfg(..., 60)
  ```
  - **Status:** ✅ Already configurable via env/config
  - **Context:** This is a fallback default

**File:** `main.py`
- **Line 648:** `5` - TOTP confirmation limit
- **Line 656:** `3` - Recovery code regeneration limit  
- **Line 3342, 3520:** `30` - Remember device days
- **Line 4674:** `6` - TOTP digits
- **Line 4675:** `30` - TOTP time step (seconds)

#### Rate Limiting & Abuse Prevention
**File:** `restailor/app_config.py` (Lines 451-453)
```python
cap_residential_per_ip: int = 5    # 24h cap for residential IPs
cap_university_per_ip: int = 20    # 24h cap for university IPs
cap_unknown_per_ip: int = 3        # 24h cap for unknown IPs
```
**Recommendation:** Consider extracting to a dedicated `RateLimitConfig` section

#### Credit Grant Windows
**File:** `main.py`
- **Line 10041:** `7` - Email grant window (days)
- **Line 10042:** `30` - Fingerprint grant window (days)

---

### 🟡 MEDIUM PRIORITY - Business Logic

#### HTTP Status Codes
Multiple files contain hardcoded HTTP status codes:
- `400` (Bad Request) - ~30 occurrences
- `401` (Unauthorized) - ~25 occurrences
- `402` (Payment Required) - ~5 occurrences
- `403` (Forbidden) - ~10 occurrences
- `404` (Not Found) - ~8 occurrences
- `409` (Conflict) - ~12 occurrences
- `413` (Payload Too Large) - ~3 occurrences
- `429` (Too Many Requests) - ~4 occurrences
- `500` (Internal Server Error) - ~15 occurrences

**Recommendation:** Consider creating an enum or constants module:
```python
class HTTPStatus:
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    PAYMENT_REQUIRED = 402
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    PAYLOAD_TOO_LARGE = 413
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
```

#### Time Conversions
**Multiple files** contain time conversion calculations:
- `24 * 60 * 60` (seconds in day) - 8+ occurrences
- `24 * 3600` (seconds in day, alternate) - 15+ occurrences  
- `7 * 24 * 3600` (seconds in week) - 4+ occurrences
- `days * 24 * 3600` (variable days to seconds) - 10+ occurrences

**Recommendation:** Create time constants:
```python
# constants.py
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 60 * 60
SECONDS_PER_DAY = 24 * 60 * 60
SECONDS_PER_WEEK = 7 * SECONDS_PER_DAY
MILLISECONDS_PER_SECOND = 1000
```

#### Worker Coalescing
**File:** `worker.py`
- **Line 4:** `max(20, min(500, _get_env_int("RT_COALESCE_MS", 100)))`
  - Min: `20` ms
  - Max: `500` ms  
  - Default: `100` ms
- **Line 130:** `1000.0` - Millisecond conversion factor

**Recommendation:** Extract to worker configuration constants

---

### 🟢 LOW PRIORITY - Test & Development

#### Test Sleep/Delays
**File:** `tests/` (various)
- `time.sleep(0.1)` - Brief synchronization delay
- `time.sleep(0.5)` - Half-second delay for UI stabilization
- `time.sleep(2)` - Standard test wait
- `time.sleep(3)` - Extended UI wait
- `time.sleep(5)` - Stripe webhook wait

**Recommendation:** Create test constants:
```python
# tests/conftest.py or test_constants.py
class TestWaitTimes:
    BRIEF = 0.1
    SHORT = 0.5
    STANDARD = 2
    UI_INTERACTION = 3
    WEBHOOK = 5
```

#### Test Iterations
Common patterns:
- `range(3)` - Small iteration tests
- `range(5)` - Medium iteration tests
- `range(6)` - Recovery code tests
- `range(36)` - Long-running Stripe tests (3 minutes at 5s intervals)

#### Frontend Token Management
**File:** `frontend/lib/tokenRefresh.ts`
```typescript
const ACCESS_TOKEN_MINUTES = parseInt(process.env.NEXT_PUBLIC_ACCESS_TOKEN_MINUTES || '60', 10);
const REFRESH_INTERVAL_MS = ACCESS_TOKEN_MINUTES * 60 * 1000 * 0.75;
```
- `60` - Default access token lifetime (minutes)
- `1000` - Milliseconds conversion
- `0.75` - Refresh at 75% of token lifetime

**Status:** Already well-structured, uses env var override

---

### ⚪ ACCEPTABLE - Domain Constants

These numbers have clear semantic meaning in context:

#### String Slicing/Truncation
- `[:8]`, `[:16]`, `[:20]` - Hash/token display truncation
- `[:200]` - Error message truncation for logging
- `[:500]` - Analytics snippet cap

**Context:** These are presentation/logging limits, acceptable as-is

#### Data Validation Limits
- `max_length=200` (bulk items) - Business constraint
- `len(set(pw)) <= 2` - Password complexity check

#### Mathematical Constants
- **File:** `services/pricing.py` Line 15: `getcontext().prec = 28`
  - Decimal precision for financial calculations
  - **Status:** ✅ Appropriate for Decimal context

#### Minimum Thresholds
- **File:** `services/postprocess.py`
  ```python
  MIN_RESUME_CHARS: int = 16
  MIN_BULLETS: int = 5
  OVERLAP_SAMPLE_STEP: int = 20
  ```
  - **Status:** ✅ Well-named constants already

---

## Async Sleep Patterns

Multiple files use `await asyncio.sleep(0)` to yield control:
- `worker.py` - 4 occurrences
- `services/llm.py` - 1 occurrence
- `restailor/sse_utils.py` - 1 occurrence
- Old archived scripts - 3 occurrences

**Context:** `asyncio.sleep(0)` is idiomatic Python for cooperative yielding. No change needed.

---

## Frontend Analysis

**File:** `frontend/lib/` (TypeScript/JavaScript)

### Time Constants
- Token refresh: `60 * 1000` (1 minute in ms)
- Backoff: `500` ms starting delay
- Cookie max age: `365 * 24 * 60 * 60` (1 year in seconds)

### HTTP Status References
Multiple references to `401` in comments and error handling (appropriate for auth flow documentation)

---

## Recommendations by Priority

### Immediate Actions
1. **Extract rate limit constants** from `app_config.py` to named config section
2. **Create HTTPStatus enum** for consistent status code usage
3. **Define time conversion constants** in a shared module

### Short-term Improvements
1. **Consolidate test wait times** into test utilities
2. **Document worker coalescing parameters** with inline comments
3. **Review and standardize string truncation limits**

### Long-term Considerations
1. Create a `constants.py` module for cross-cutting numeric values
2. Consider config-driven test timeouts for CI flexibility
3. Audit and potentially extract frontend magic numbers to config

---

## Files Requiring Attention

### High Priority
1. `restailor/app_config.py` - Rate limiting caps
2. `main.py` - MFA limits, grant windows
3. `restailor/security.py` - Token expiration defaults

### Medium Priority
1. `worker.py` - Coalescing parameters
2. `restailor/input_gate.py` - HTTP status codes
3. `restailor/applications_api.py` - HTTP status codes

### Low Priority (Test Files)
1. `tests/test_admin_stepup_and_trusted_devices.py`
2. `tests/test_sidebar_hydration_and_save.py`
3. `tests/test_stripe_manual.py`

---

## Notes

- Many magic numbers are already wrapped in configuration or environment variable fallbacks
- HTTP status codes are used idiomatically with FastAPI's `HTTPException`
- Time conversions are the most common pattern that could benefit from standardization
- Test sleep delays are acceptable but could benefit from named constants for maintainability

---

## Next Steps

1. Review this document with the team
2. Prioritize which constants to extract first
3. Create PR to address high-priority items
4. Establish coding standards for new numeric literals

