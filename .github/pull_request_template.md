# Analytics Source of Truth - Remove Backdoors

## Overview
This PR establishes analytics tables as the **single source of truth** for downstream data warehouse consumption by removing all UI-based export mechanisms and CSV endpoints that bypass our controlled analytics layer.

## Objectives
- ✅ Enforce analytics layer as the only external data source
- ✅ Establish clear data contracts for warehouse consumers
- ✅ Prevent accidental PII leakage through ad-hoc exports
- ✅ Enable proper access control via `analytics_reader` role
- ✅ Add CI guardrails to prevent regression

---

## Checklist

### 1️⃣ Remove UI Console Exporters
- [ ] Remove CSV export from Applications History page
- [ ] Remove JSON export from Applications History page
- [ ] Remove any Excel/spreadsheet export buttons
- [ ] Remove browser console data dumpers (if any)
- [ ] Audit frontend for `downloadAs*` or `exportTo*` utility functions
- [ ] Update user documentation to remove export references

**Files to check:**
- `frontend/src/pages/**/history*`
- `frontend/src/components/**/export*`
- `frontend/src/utils/download*`

---

### 2️⃣ Remove CSV Backend Endpoints
- [ ] Remove `/api/export/applications/csv` endpoint (if exists)
- [ ] Remove `/api/export/history/csv` endpoint (if exists)
- [ ] Remove any `/api/*/download` endpoints that serve raw data
- [ ] Remove helper functions like `generate_csv`, `to_csv`, `export_*`
- [ ] Update API documentation to reflect removed endpoints
- [ ] Add deprecation notices if phased removal needed

**Files to check:**
- `services/api/routes/export*.py`
- `services/api/routes/applications*.py`
- `main.py` (FastAPI route registration)

---

### 3️⃣ Add Analytics Schema & Materialized Views
- [ ] Create `analytics` schema (if not exists)
- [ ] Create `analytics.job_applications_latest` materialized view
  - Deduplicate by `(user_id, jd_hash)` keeping latest snapshot
  - Join with `jobs` table for latest state flags
  - Compute `final_hired`, `final_offer`, `final_interviewing`, `is_active`
  - Add `exclusion_reason` for filtered records
- [ ] Create `analytics.user_funnel_summary` materialized view
  - Aggregate counts by `user_id`
  - Include: `snapshot_count`, `is_applied`, `is_interviewing`, `is_offer`, `is_hired`
- [ ] Add refresh triggers or scheduled job (e.g., via cron or ARQ task)
- [ ] Document MV refresh strategy in `docs/DB.md`

**SQL Reference:**
```sql
-- See queries/History and Analytics Check.sql for deduplication logic
-- Adapt the CTE-based query into a CREATE MATERIALIZED VIEW statement
```

---

### 4️⃣ Add `analytics_reader` Role & Privileges

#### Option A: Manual Runbook (Quick Start)
- [ ] Create `docs/ANALYTICS_READER_SETUP.md` runbook with:
  - `CREATE ROLE analytics_reader NOLOGIN;`
  - `GRANT USAGE ON SCHEMA analytics TO analytics_reader;`
  - `GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader;`
  - `ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO analytics_reader;`
  - Instructions for DBA to grant role to warehouse service account
- [ ] Add note in `README.md` linking to the runbook

#### Option B: Alembic Migration (Production-Ready)
- [ ] Generate migration: `alembic revision -m "add_analytics_reader_role"`
- [ ] Implement `upgrade()`:
  - Create role if not exists
  - Grant schema usage
  - Grant SELECT on existing analytics tables
  - Set default privileges for future tables
- [ ] Implement `downgrade()`:
  - Revoke privileges
  - Drop role (with CASCADE or after manual reassignment)
- [ ] Test migration on local dev DB
- [ ] Document in `docs/DEPLOYMENT.md`

**Choose one approach and check the relevant boxes.**

---

### 5️⃣ Add CI Guard Against Exporter Patterns
- [ ] Create `.github/workflows/ban-exporters.yml`
- [ ] Add grep check for forbidden patterns:
  - `downloadCSV`, `exportCSV`, `toCSV`, `generateCSV`
  - `/api/export/`, `/download/`, `Content-Disposition: attachment`
- [ ] Exclude allowed patterns (if any, e.g., admin audit logs)
- [ ] Configure to run on PR and push to `main`/`dev`
- [ ] Test CI by intentionally adding a forbidden pattern and reverting

**Example CI snippet:**
```yaml
- name: Ban exporter patterns
  run: |
    if grep -r "downloadCSV\|exportCSV" frontend/src; then
      echo "❌ Found forbidden export pattern in frontend"
      exit 1
    fi
    if grep -r "/api/export/" services main.py; then
      echo "❌ Found forbidden export endpoint in backend"
      exit 1
    fi
```

---

### 6️⃣ Add Source Contract Documentation
- [ ] Create `docs/ANALYTICS_SOURCE_CONTRACT.md`
- [ ] Document each analytics table/view:
  - Column definitions and types
  - Refresh schedule (if materialized)
  - SLAs (data freshness guarantees)
  - Known limitations or edge cases
- [ ] Include example queries for common use cases
- [ ] Add versioning strategy (e.g., semantic versioning for schema changes)
- [ ] Define breaking vs. non-breaking change policy
- [ ] Add contact/ownership info (team/email for questions)

**Template Outline:**
```markdown
# Analytics Source Contract

## Version: 1.0.0

### `analytics.job_applications_latest`
- **Description**: Deduplicated application snapshots with latest job state
- **Refresh**: Every 15 minutes
- **Columns**: [user_id, snapshot_id, jd_hash, is_applied, final_hired, ...]
- **SLA**: 99.5% uptime, < 20 min data lag
- **Breaking Changes**: Requires major version bump + 30-day deprecation notice

### `analytics.user_funnel_summary`
...
```

---

## Testing & Validation
- [ ] Verify analytics MVs return expected data (compare with old query results)
- [ ] Confirm `analytics_reader` role can SELECT but not INSERT/UPDATE/DELETE
- [ ] Test that removed export endpoints return 404/410 Gone
- [ ] Run CI guard workflow and confirm it catches forbidden patterns
- [ ] Manual QA: ensure History page still renders correctly (no export buttons)

---

## Rollout Plan
1. **Deploy backend** with analytics MVs first (non-breaking)
2. **Grant `analytics_reader`** to warehouse service account
3. **Update warehouse ETL** to consume from analytics schema
4. **Deploy frontend** with export buttons removed (after warehouse cutover)
5. **Monitor** for 48 hours; roll back if critical issues

---

## Rollback Strategy
- Analytics MVs: Can be dropped without affecting core app (no foreign keys)
- Removed endpoints: Restore from git if urgent need arises (temporary)
- `analytics_reader` role: Harmless to leave in place even if unused

---

## Related Issues
- Closes #XXX (link to GitHub issue if exists)
- Related to data warehouse migration initiative

---

## Screenshots / Evidence
_Add before/after screenshots of History page (no export buttons after)_

---

## Reviewer Checklist
- [ ] Code follows project style guidelines
- [ ] All tests pass (backend + frontend)
- [ ] Analytics MVs tested on staging data
- [ ] CI guard workflow tested and enabled
- [ ] Documentation is clear and complete
- [ ] Rollout plan approved by stakeholders
