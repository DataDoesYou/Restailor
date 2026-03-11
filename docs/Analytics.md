# Analytics Integration

Complete guide for analytics data access, security controls, and data warehouse integration.

**Last Updated:** October 17, 2025

---

## Quick Start (Data Warehouse Teams)

### Connect to Analytics Schema

**PostgreSQL Connection:**
```
postgres://analytics_reader:PASSWORD@host:5432/restailor?sslmode=require
```

**Access:** Read-only `analytics` schema (no PII, safe for DW integration)

### Available Data

**Materialized View:** `analytics.mv_applications` (16 columns)

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Application ID |
| `user_id` | INTEGER | User who owns application |
| `company` | TEXT | Company name |
| `role` | TEXT | Job role/title |
| `is_applied` | BOOLEAN | Marked as submitted |
| `is_interviewing` | BOOLEAN | Marked as interviewing |
| `is_offer` | BOOLEAN | Marked as received offer |
| `is_hired` | BOOLEAN | Marked as hired |
| `created_at` | TIMESTAMPTZ | Creation timestamp (UTC) |
| `updated_at` | TIMESTAMPTZ | Last modified (UTC) |
| ...and 6 more |

**Excluded (PII):** `snapshot_enc`, `jd_text_norm`, test data

### Incremental Pull

```sql
-- Initial load
SELECT * FROM analytics.mv_applications
ORDER BY updated_at, id;

-- Incremental (subsequent runs)
SELECT * FROM analytics.mv_applications
WHERE updated_at > :last_watermark
ORDER BY updated_at, id;
```

**Recommended frequency:** Every 10-15 minutes

---

## Security Architecture

### Why No CSV Exports?

**Previous Problem:**
- Frontend had `window.__exportStageAnalytics()` debug helpers
- Backend had `/analytics/export.csv` API endpoint
- **Risks:** PII leakage, no audit logs, uncontrolled data access

**Current Solution:**
- All analytics via PostgreSQL `analytics` schema only
- Curated, non-PII data with access controls
- All queries logged and auditable
- Role-based access (`analytics_reader`)

### Three-Layer Defense

#### Layer 1: Runtime Guard (Browser)
```typescript
// Throws error in production if export helpers found
assertNoExports();  // Checks window.__export*, exportCsv, etc.
```

#### Layer 2: CI Source Code Scanner
```bash
npm run ci:forbid-exporters
# Blocks patterns: window.__export*, exportCsv, toCSV, text/csv, etc.
```

#### Layer 3: Production Bundle Verification
```bash
npm run ci:verify-bundle
# Scans compiled .next bundle for export patterns
```

**All three layers run automatically in CI/CD**

---

## Analytics Schema Reference

### Materialized View Definition

```sql
CREATE MATERIALIZED VIEW analytics.mv_applications AS
SELECT
    id, user_id, job_id, company, role, jd_url,
    jd_snippet, jd_hash, base_hash, applied_key,
    is_applied, is_interviewing, is_offer, is_hired,
    created_at, updated_at
FROM public.applications
WHERE COALESCE(is_test, false) = false;  -- Exclude test data
```

**Refresh:** Every 5-15 minutes (concurrent, non-blocking)

### Indexes

```sql
-- Primary (enables concurrent refresh)
CREATE UNIQUE INDEX ix_mv_applications_id ON analytics.mv_applications (id);

-- Query optimization
CREATE INDEX ix_mv_applications_updated_at ON analytics.mv_applications (updated_at DESC);
CREATE INDEX ix_mv_applications_user_id ON analytics.mv_applications (user_id);
CREATE INDEX ix_mv_applications_created_at ON analytics.mv_applications (created_at DESC);

-- Partial (only TRUE/non-NULL values)
CREATE INDEX ix_mv_applications_is_applied 
  ON analytics.mv_applications (is_applied) WHERE is_applied = true;
CREATE INDEX ix_mv_applications_job_id 
  ON analytics.mv_applications (job_id) WHERE job_id IS NOT NULL;
```

### Access Control

**Role:** `analytics_reader`

**Privileges:**
- ✅ SELECT on `analytics` schema
- ❌ No access to `public` schema (base tables)
- ❌ No write operations
- ❌ No DDL operations

**Safety Settings:**
```sql
ALTER ROLE analytics_reader SET statement_timeout = '30s';
ALTER ROLE analytics_reader SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE analytics_reader SET default_transaction_read_only = ON;
```

**Connection Limits:** Max 5 connections, 10-minute idle timeout

---

## Data Warehouse Integration

### Incremental ETL Pattern

**High-Water Mark Strategy:**

```python
# 1. Initial full load
df = pd.read_sql(
    "SELECT * FROM analytics.mv_applications ORDER BY updated_at, id",
    engine
)

# 2. Store watermark
watermark = df['updated_at'].max()

# 3. Incremental updates
df_incr = pd.read_sql(
    "SELECT * FROM analytics.mv_applications WHERE updated_at > %(wm)s",
    engine,
    params={'wm': watermark}
)

# 4. Update watermark
if not df_incr.empty:
    watermark = df_incr['updated_at'].max()
```

### Recommended Cadence

| Data Volume | Inserts/Hour | Pull Interval |
|-------------|--------------|---------------|
| < 10k rows | < 100/hour | 15 minutes |
| 10k - 100k | 100-1k/hour | 10 minutes |
| 100k - 1M | 1k-10k/hour | 5 minutes |
| > 1M | > 10k/hour | Contact platform team |

### dbt Example

```sql
-- models/staging/stg_applications.sql
{{
    config(
        materialized='incremental',
        unique_key='id',
        on_schema_change='fail'
    )
}}

SELECT * FROM {{ source('analytics', 'mv_applications') }}

{% if is_incremental() %}
WHERE updated_at > (SELECT MAX(updated_at) FROM {{ this }})
{% endif %}
```

### Airbyte/Fivetran

**Source:** PostgreSQL  
**Replication:** INCREMENTAL  
**Cursor Field:** `updated_at`

```json
{
  "host": "replica.example.com",
  "database": "restailor",
  "schema": "analytics",
  "username": "analytics_reader",
  "ssl": true
}
```

---

## Data Freshness & SLA

**Standard SLA:**
- Data is at most **15 minutes stale**
- Typically refreshed within 5-10 minutes

**Health Check:**
```sql
SELECT MAX(updated_at) as last_update
FROM analytics.mv_applications;
-- Expected: Within last 15-20 minutes
```

**Monitoring:**
```sql
-- Data freshness
SELECT NOW() - MAX(updated_at) as staleness
FROM analytics.mv_applications;
-- Alert if > 20 minutes

-- Row count sanity check
SELECT COUNT(*) as row_count
FROM analytics.mv_applications;
-- Alert if drops >10% from previous day
```

---

## Schema Evolution & Breaking Changes

**Current Version:** 1.0.0

**Versioning:**
- **Major (X.0.0):** Breaking changes (column removal, type change)
- **Minor (1.X.0):** Additive changes (new columns, indexes)
- **Patch (1.0.X):** Documentation updates

**Breaking Change Process:**
1. **30 days advance notice** via email + Slack
2. **60-day migration window** (both old/new schemas available)
3. **Updated documentation** published before change
4. **Rollback plan** prepared and communicated

**Planned Roadmap:**
- v1.1.0: Add `applied_date`, `interviewed_date`, `offer_date`, `hired_date` timestamps
- v1.2.0: Add `industry` (company industry classification)
- v2.0.0: Split into `mv_applications` + `mv_application_events` (event sourcing)

---

## Performance Best Practices

### Query Optimization

✅ **Good (Uses Index):**
```sql
SELECT id, user_id, created_at
FROM analytics.mv_applications
WHERE updated_at > '2025-10-16 10:00:00+00'
ORDER BY updated_at, id
LIMIT 10000;
```

❌ **Bad (Full Scan):**
```sql
SELECT *
FROM analytics.mv_applications
WHERE company ILIKE '%Tech%'
ORDER BY created_at;
```

### Connection Pooling

```python
engine = create_engine(
    "postgresql://analytics_reader:PASSWORD@host:5432/restailor",
    pool_size=3,           # 2-5 connections
    max_overflow=2,        # Burst capacity
    pool_pre_ping=True,    # Test connections
    pool_recycle=1800,     # 30 min max lifetime
)
```

### Use Read Replica

**Benefits:**
- Reduces load on primary database
- No risk to application performance
- Minimal lag (<1 second) acceptable for analytics

**Contact ops for replica endpoint**

---

## Troubleshooting

**Query Timeout:**
- Add `LIMIT` clause
- Use indexed columns in `WHERE`
- Batch large extracts (10k-50k rows per query)

**Permission Denied:**
- Verify role grants with platform team
- Check connection string uses `analytics_reader`

**Stale Data (>20 minutes):**
- Check with platform team for MV refresh status
- Review health check query results

**Connection Limit Exceeded:**
- Implement connection pooling
- Reduce pool size
- Check for connection leaks

---

## Testing & Verification

### Backend Integration Tests

**File:** `tests/test_csv_export_removed.py`

Tests verify:
- `/analytics/export.csv` returns 404
- No CSV content-type headers in analytics routes
- All HTTP methods (GET/POST/PUT/DELETE) removed

```bash
doppler run -- poetry run pytest tests/test_csv_export_removed.py -v
```

### Analytics View Safety Tests

**File:** `tests/test_analytics_views_safety.py`

Tests verify:
- Only 16 safe columns exposed
- PII excluded (`snapshot_enc`, `jd_text_norm`)
- Test data filtered (`is_test = false`)
- Read-only enforcement (cannot INSERT/UPDATE/DELETE)

```bash
doppler run -- poetry run pytest tests/test_analytics_views_safety.py -v
```

### Frontend Build Tests

**File:** `frontend/test/no-exporters-in-prod.test.ts`

Tests verify:
- Production build tree-shaking
- Runtime guard functionality
- No export helpers in compiled bundle

```bash
npm --prefix frontend run test
```

---

## Security & Credential Management

### Credential Rotation

**Schedule:** Quarterly (every 90 days)

**Process:**
1. Generate new password (32+ chars)
2. Update in secrets manager
3. Notify DW team (7-day advance)
4. Update in database
5. Monitor connections
6. Revoke old credentials after 7 days

### Network Security

**Recommendations:**
- IP allowlist in `pg_hba.conf`
- Require SSL/TLS
- Use connection pooler (PgBouncer, RDS Proxy)
- Enable query logging for audit

**Example pg_hba.conf:**
```
hostssl  restailor  analytics_reader  10.0.5.0/24  scram-sha-256
hostssl  restailor  analytics_reader  10.0.6.0/24  scram-sha-256
hostssl  restailor  analytics_reader  0.0.0.0/0    reject
```

---

## Support

**Platform Team:**
- Email: platform-team@example.com
- Slack: #data-platform

**SLA:**
- Non-urgent: 1 business day response
- Access issues: 3 business days resolution
- Production outage: 1 hour response

---

## FAQ

**Q: Can I query base tables directly?**  
A: No. `analytics_reader` only has access to `analytics` schema.

**Q: Can I write to the materialized view?**  
A: No. Materialized views are read-only.

**Q: What if I need more columns?**  
A: Contact platform team. Non-PII columns can be added (non-breaking).

**Q: Data retention policy?**  
A: No retention policy. Historical data preserved indefinitely.

**Q: Can I use Airbyte/Fivetran?**  
A: Yes. Use JDBC connector with incremental mode.

**Q: Is there a Parquet export?**  
A: No. Source is PostgreSQL only. DW team handles format conversion.

**Q: Why were CSV exports removed?**  
A: Security risk (PII leakage, no audit logs). Use analytics schema instead.

---

**Related Documentation:**
- [Architecture](architecture.md)
- [Security](Security.md)
- [Database Setup](DB.md)
- [Deployment](DEPLOYMENT.md)
