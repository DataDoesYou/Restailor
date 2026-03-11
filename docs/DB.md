# Database Guide

This document covers the schema, ERD, encrypted fields, indexes, and migration workflow.

## Schema overview

Tables
- users
- jobs
- job_outputs
- charges
- credit_ledger
- user_balance
- email_logs
- audit_events
- applications
- analytics_job_snapshot_state
- (additional tables created by migrations, e.g., webauthn_credentials, user_trusted_devices, email_otps)
 - webauthn_credentials (passkey public keys + sign counters)
 - user_trusted_devices (hashed device tokens + policy metadata)
 - email_otps (pending OTP codes with expiry / attempt counters)

## ERD (Mermaid)

```mermaid
erDiagram
  users ||--o{ jobs : has
  jobs ||--o{ job_outputs : yields
  users ||--o{ credit_ledger : updates
  users ||--|| user_balance : owns
  users ||--o{ email_logs : receives
  users ||--o{ audit_events : emits
  users ||--o{ webauthn_credentials : authenticates
  users ||--o{ user_trusted_devices : remembers
  jobs ||--o{ charges : billed

  users {
    int id PK
    string username UK
    string hashed_password
    bool is_verified
    bool is_email_verified
    string email_verification_token
    string browser_fingerprint
    int credits
    bool public_profile
    bool dont_save_future_data
    string role
    timestamptz deleted_at
    timestamptz credits_forfeited_at
    bytea last_resume_enc
    bytea last_jd_enc
    bool is_test
    timestamptz created_at
    timestamptz updated_at
  }
  jobs {
    uuid id PK
    string status
    timestamptz created_at
    timestamptz updated_at
    string input_hash
    string job_flow
    string source_page
    bytea resume_enc
    bytea jd_enc
    bytea candidate_enc
    float cost
    int latency_ms
    string access_token
    string client_id
    bool is_test
    int user_id FK
  }
  job_outputs {
    uuid id PK
    uuid job_id FK
    string type
    bytea content_enc
    timestamptz created_at
    float cost
    int latency_ms
    bool is_test
  }
  charges {
    uuid id PK
    timestamptz created_at
    int user_id FK
    uuid job_id FK
    text request_type
    text provider
    text model
  int model_count
    int prompt_tokens
    int completion_tokens
    numeric(12,6) cost_usd
    numeric(12,6) price_to_user_usd
    text currency
    int pricing_version
    bool is_test
  }
  credit_ledger {
    uuid id PK
    timestamptz created_at
    int user_id FK
    int delta_cents
    text type
    text note
    text provider_ref
    int admin_id FK
    bool is_test
  }
  user_balance {
    int user_id PK, FK
  int balance_cents  // internal running balance for locking/write flows; user-visible reads compute fresh from ledger-charges
    timestamptz created_at
    timestamptz updated_at
    bool is_test
  }
  email_logs {
    uuid id PK
    timestamptz created_at
    int user_id FK
    text recipient
    text subject
    string kind
    string source
    string status
    text error
    string client_id
    string ip
    bool is_test
  }
  audit_events {
    bigint id PK
    timestamptz created_at
    int user_id FK
    text event_type
    text severity
    text ip
    text user_agent
    jsonb meta
    bool is_test
  }
  applications {
    int id PK
    int user_id FK
    text company
    text role
    text jd_url
    bool is_applied
    bool is_interviewing
    bool is_offer
    bool is_hired
    bool is_test
    timestamptz created_at
    timestamptz updated_at
    jsonb snapshot_enc (encrypted)
    jsonb job_input_hashes
    text jd_hash
    text base_hash
    text applied_key_canonical
    int job_id FK (nullable)
  }
  analytics_job_snapshot_state {
    int snapshot_id FK (applications.id)
    int user_id FK
    uuid job_id FK
    timestamptz created_at
    timestamptz updated_at
    bool is_applied
    bool is_active
    bool is_interviewing
    bool is_offer
    bool is_hired
    bool is_test
  }
  jobs {
    uuid id PK
    // ... other fields ...
    bool is_interviewing
    bool is_offer
    bool is_hired
    bool is_archived
    timestamptz deleted_at
  }
```

Encrypted columns at rest (via pgcrypto + app-side key management)
- users.last_resume_enc, users.last_jd_enc
- jobs.resume_enc, jobs.jd_enc, jobs.candidate_enc
- job_outputs.content_enc
- applications.snapshot_enc

Indexes (non-exhaustive)
- jobs: status, job_flow, source_page, user_id, input_hash
- applications: user_id, jd_hash, applied_key, is_applied, job_input_hashes(jsonb_path_ops)
- job_outputs: job_id, type
- charges: (request_type, model, created_at desc), (user_id, created_at desc)
- credit_ledger: (user_id, created_at desc), provider_ref, (admin_id, created_at desc)
- email_logs: created_at desc, recipient, kind, source, status
- audit_events: created_at desc, event_type

## Migrations

- Autogenerate
  - `poetry run alembic revision --autogenerate -m "your change"`
- Apply
  - `poetry run alembic upgrade head`
- Downgrade
  - `poetry run alembic downgrade -1`

Safety
- Migrations are idempotent and use naming conventions for constraints
- pgcrypto extension must be present; initial migrations enable it

Backups and data hygiene
- Set PII_ENCRYPTION_KEY and rotate using dual-write strategy in a future migration if needed
- Test data is marked with is_test=true for safe cleanup

## Key Schema Changes (Single Source of Truth)

**Applications Table - Primary Stage Source**
- Added stage flag columns: `is_interviewing`, `is_offer`, `is_hired` (alongside existing `is_applied`)
- These flags are the canonical source; jobs table flags cascade to applications
- `jd_hash`: Primary deduplication key (one application per user + JD)
- `base_hash`: Normalized JD hash for matching similar postings
- `applied_key_canonical`: Stable identifier for applied status tracking
- `job_input_hashes`: JSONB storing hash hints to avoid redundant PII decrypts
- Unique constraint: `(user_id, jd_hash)` ensures single application per JD

**Jobs Table Updates**
- Added stage columns: `is_interviewing`, `is_offer`, `is_hired`, `is_archived`
- When job stage changes, update cascades to all linked applications
- `deleted_at`: Soft delete timestamp for archival

**Analytics Snapshot State**
- Denormalized view for fast analytics queries
- `is_active`: Filters out archived/deleted/test jobs
- Rebuilt via `services/analytics_job_snapshot.py`
- Stage flags match applications table via shared `stage_utils` helpers

**Recent Migrations**
- `20251008_applications_job_hash_hints`: Added job_input_hashes column
- `20251007_applications_stage_cleanup`: Added stage flag columns to applications
- `20251006_add_job_stage_columns`: Added stage flags to jobs table
- `20251005_single_snapshot_per_jd`: Enforced unique constraint on (user_id, jd_hash)
- `20251001_0900_snapshot_is_active`: Added is_active flag to analytics

---

CHANGELOG
- 2025-10-03: Major update for Single Source of Truth architecture - documented stage flag columns, cascade updates, hash hint system, and recent migrations.
- 2025-09-26: Added applications + analytics snapshot tables, documented `job_input_hashes` column and related index guidance.
- 2025-09-11: Clarified job_flow enumeration and benchmark multi-model `charges.model_count` usage.
- 2025-09-07: Listed webauthn_credentials, user_trusted_devices, email_otps explicitly; clarified indexes.
- 2025-09-02: Initial DB guide with ERD and migration workflow.

### Migration Validation & Conventions

To keep the Alembic history healthy and CI-friendly:

1. Revision ID length: Must be <= 32 characters (the `alembic_version.version_num` column is `VARCHAR(32)`).
2. Every `down_revision` (or each element of a tuple for merge migrations) must point to an existing revision file.
3. Merge migrations (tuple `down_revision`) should be used only to join diverging heads; prefer linear history when feasible.
4. Placeholder / lost migrations: If a historical revision was lost but its effects are already in the database, add a no-op placeholder with the original revision ID so newer migrations can proceed without manual DB surgery.
5. Do not rename revision IDs after they ship—except to shorten them before first successful application everywhere (see below). If you must adjust, ensure no environment has applied the old ID (or manually reconcile those environments first).

Automated check:

```
python scripts/check_migrations.py
```

The script fails (exit 1) and prints JSON if:
- A revision id is > 32 chars
- A dependency is missing
- A duplicate revision id is detected

Integrate in CI (GitHub Actions example step):

```
- name: Validate migrations
  run: python scripts/check_migrations.py
```

### Shortened Revision Note (2025-09-06)

The normalization migration originally used a long ID: `20250906_normalize_judge_req_type` ( > 32 chars ) which failed to persist in `alembic_version`. It was shortened to `20250906_norm_judge_req_type` before broad deployment. Ensure any future migrations reference the shortened ID in their `down_revision`.

If an environment previously attempted the long ID and failed, simply pull latest and run:

```
poetry run alembic upgrade head
```

No manual cleanup is required because the failing step never wrote a row to `alembic_version`.

---
Additional best practices:
- Prefer additive changes; avoid destructive column drops without a deprecation window.
- Use `server_default` sparingly—migrate data explicitly when semantics matter.
- For large backfills, split schema vs data migrations to keep deploy steps fast.
- Mark irreversible data rewrites with comments and `# pragma: no cover` where appropriate.

---

## Token Billing

### Overview
The application uses a **hybrid billing approach** that prefers real provider-reported tokens when available, with intelligent fallback to estimates.

### Billing Decision Tree
1. Collect estimated tokens (always, for fallback)
2. Execute LLM request
3. Capture real tokens from provider (if available)
4. Store charge with both estimates and real values
5. Debit decision:
   - **IF** `prompt_tokens_real` AND `completion_tokens_real` both exist → Use `price_to_user_usd_real` (REAL BILLING)
   - **ELSE** → Use `price_to_user_usd` (ESTIMATE FALLBACK)

### Provider Token Capture

| Provider | Real Tokens Captured | Method |
|----------|---------------------|--------|
| **OpenAI** | ✅ Both prompt & completion | `usage` object after stream completion |
| **Anthropic** | ✅ Both prompt & completion | `usage` object after stream completion |
| **xAI** | ✅ Both prompt & completion | `usage` object after stream completion |
| **Google Gemini** | ⚠️ Prompt only | `count_tokens()` API, completion estimated |

All providers store tokens via `_store_usage()` function with Redis fallback.

### Token Estimation Methods

**For estimates (when real tokens unavailable):**
1. **tiktoken** (OpenAI models): Uses `tiktoken` library with model-aware encoding
   - GPT-4, GPT-3.5, O1, O3: `cl100k_base` encoding
   - Older models: `p50k_base` encoding
   - Accuracy: ~95%+

2. **Character heuristic** (fallback): `len(text) / 4`
   - Used when tiktoken unavailable or errors
   - Conservative estimate (typically over-estimates)

3. **Minimum token count**: Always returns at least 1 token

### Charge Schema

```sql
-- charges table (excerpt)
CREATE TABLE charges (
    id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    user_id INT REFERENCES users(id),
    
    -- Estimated tokens (always present)
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    price_to_user_usd DECIMAL(10,8) NOT NULL,
    
    -- Real tokens (when available from provider)
    prompt_tokens_real INT,
    completion_tokens_real INT,
    price_to_user_usd_real DECIMAL(10,8),
    
    -- Debit amount
    debit_cents INT NOT NULL,  -- Uses real price if both *_real exist, else estimate
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Analytics Queries

All analytics functions prefer real prices over estimates:

```sql
-- Example: median_last100_price()
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY effective_price)
FROM (
    SELECT COALESCE(price_to_user_usd_real, price_to_user_usd) AS effective_price
    FROM charges
    WHERE user_id = ? AND model_id = ?
    ORDER BY created_at DESC
    LIMIT 100
) subquery;
```

Functions using this pattern:
- `median_last100_price()`
- `trimmed_average_last100_price()`
- `last100_avg_by_request_and_model()`

### Enhanced Logging

Billing logs track the billing method used:

```json
{
  "evt": "charge_persisted",
  "billing_method": "real_tokens",  // or "estimated_tokens"
  "prompt_tokens_est": 1500,
  "completion_tokens_est": 800,
  "prompt_tokens_real": 1523,
  "completion_tokens_real": 789,
  "price_est_usd": "0.024500",
  "price_real_usd": "0.024180",
  "debit_cents": 2,
  "token_estimation_method": "provider_usage"
}
```

### Admin Monitoring

**Endpoint:** `GET /admin/token_billing_stats`  
**Auth:** Requires admin + stepup token

Returns:
- Total charges and breakdown (real/estimated/partial)
- Real token percentage
- Average estimation error
- Total under/over charging amounts
- Count of under/over charged requests

Example response:
```json
{
  "total_charges": 1523,
  "real_billing_count": 1204,
  "estimate_billing_count": 319,
  "partial_real_count": 15,
  "real_token_percentage": 79.05,
  "avg_estimation_error_pct": 2.34,
  "total_undercharged_usd": "12.45",
  "total_overcharged_usd": "8.23",
  "undercharged_count": 145,
  "overcharged_count": 174
}
```

### Accuracy Expectations

| Provider | Expected Accuracy |
|----------|------------------|
| OpenAI | ~95%+ (tiktoken + real tokens) |
| Anthropic | ~98%+ (real tokens from API) |
| xAI | ~98%+ (real tokens from API) |
| Gemini | ~85% (real prompt, estimated completion) |

### Implementation Files

1. **services/analytics.py** - Analytics prefer real prices
2. **services/postprocess.py** - Enhanced logging
3. **services/token_estimation.py** - tiktoken integration
4. **main.py** - Admin monitoring endpoint
5. **worker.py** - Deprecation note on `_chars_to_tokens`

### Best Practices

**Monitoring:**
- Check `/admin/token_billing_stats` regularly
- Watch for high estimation error (>20%)
- Investigate providers not returning usage data

**Development:**
- Always calculate both estimates and real prices
- Test billing logic with all token scenarios:
  - Both real tokens available
  - Only estimates available
  - Partial real tokens (one side missing)

**Troubleshooting:**
```bash
# Check billing method in logs
grep "billing_method" logs/app.log

# Verify provider token capture
grep "store_usage" logs/worker.log

# Check for estimation errors
grep "estimation_error" logs/app.log
```

### Current Limitations

1. **Gemini completion tokens**: Still estimated (provider limitation)
2. **Pre-flight checks**: Still use estimates (conservative approach)
3. **Reasoning tokens**: Not yet tracked separately (future O1/O3 support)

### Future Enhancements

1. **User-Facing Stats**: Show personal billing accuracy on dashboard
2. **Reasoning Tokens**: Separate field for O1/O3 thinking tokens
3. **Gemini Improvements**: Capture real completion tokens when API supports
4. **Real-Time Alerts**: Notify on estimation errors >20%
5. **Historical Recalculation**: Option to update old estimates with real tokens
6. **Cost Predictions**: ML model to predict costs before execution

---

**Implementation Date**: 2025-01-16  
**Status**: ✅ Complete and Production-Ready

