-- ============================================================================
-- Analytics Reader Role Setup Runbook
-- ============================================================================
-- Purpose: Create and configure analytics_reader role for data warehouse access
-- Version: 1.0.0
-- Last Updated: 2025-10-16
-- Owner: Platform Team
--
-- SECURITY NOTICE:
-- This role is intended for read-only access to curated analytics schema ONLY.
-- DO NOT grant access to:
--   - Base tables in public schema (contains PII)
--   - pgcrypto functions (encryption keys)
--   - Write privileges (INSERT, UPDATE, DELETE)
--   - DDL privileges (CREATE, DROP, ALTER)
--
-- ============================================================================

-- ============================================================================
-- STEP 1: Create Role
-- ============================================================================
-- Note: Replace '<rotate-strong-password>' with actual strong password
-- Recommendation: Use password manager or secrets vault (e.g., Doppler, Vault)
-- Password Requirements: Min 32 chars, alphanumeric + symbols, rotate quarterly

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_reader') THEN
        CREATE ROLE analytics_reader
            LOGIN
            PASSWORD '<rotate-strong-password>'  -- REPLACE THIS!
            NOINHERIT                            -- Prevent privilege escalation
            NOCREATEDB                           -- No database creation
            NOCREATEROLE                         -- No role creation
            NOREPLICATION                        -- No replication access
            CONNECTION LIMIT 5;                  -- Max 5 concurrent connections
        
        RAISE NOTICE 'Role analytics_reader created successfully';
    ELSE
        RAISE NOTICE 'Role analytics_reader already exists, skipping creation';
    END IF;
END
$$;

-- Verify role creation
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolconnlimit
FROM pg_roles
WHERE rolname = 'analytics_reader';

-- Expected output:
-- rolname: analytics_reader
-- rolsuper: f (false)
-- rolinherit: f (false - NOINHERIT set)
-- rolcreaterole: f (false)
-- rolcreatedb: f (false)
-- rolcanlogin: t (true - LOGIN enabled)
-- rolreplication: f (false)
-- rolconnlimit: 5


-- ============================================================================
-- STEP 2: Revoke Default Privileges
-- ============================================================================
-- CRITICAL: Remove all default access to public schema and base tables

-- Revoke schema-level access
REVOKE ALL ON SCHEMA public FROM analytics_reader;
REVOKE ALL ON SCHEMA public FROM PUBLIC;  -- Belt and suspenders

-- Revoke table-level access (in case schema access somehow bypassed)
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analytics_reader;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM analytics_reader;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM analytics_reader;

-- Revoke access to other sensitive schemas (adjust if your setup differs)
REVOKE ALL ON SCHEMA information_schema FROM analytics_reader;
REVOKE ALL ON SCHEMA pg_catalog FROM analytics_reader;

-- Verify no public schema access
SELECT
    has_schema_privilege('analytics_reader', 'public', 'USAGE') as has_public_usage,
    has_schema_privilege('analytics_reader', 'public', 'CREATE') as has_public_create;

-- Expected output: both should be 'f' (false)


-- ============================================================================
-- STEP 3: Grant Analytics Schema Access
-- ============================================================================
-- Allow USAGE on analytics schema (required to query objects within)

GRANT USAGE ON SCHEMA analytics TO analytics_reader;

-- Grant SELECT on all existing tables/views in analytics schema
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader;

-- Verify analytics schema access
SELECT
    has_schema_privilege('analytics_reader', 'analytics', 'USAGE') as has_analytics_usage,
    has_table_privilege('analytics_reader', 'analytics.mv_applications', 'SELECT') as can_select_mv;

-- Expected output:
-- has_analytics_usage: t (true)
-- can_select_mv: t (true)


-- ============================================================================
-- STEP 4: Configure Default Privileges for Future Objects
-- ============================================================================
-- Automatically grant SELECT on new tables/views created in analytics schema
-- This ensures new analytics objects are accessible without manual intervention

ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT SELECT ON TABLES TO analytics_reader;

-- Note: This only applies to objects created by the role that runs this command
-- If multiple roles create analytics objects, run this for each:
-- ALTER DEFAULT PRIVILEGES FOR ROLE <creator_role> IN SCHEMA analytics
--     GRANT SELECT ON TABLES TO analytics_reader;

-- Verify default privileges (query shows expected grants for future objects)
SELECT
    defaclrole::regrole AS grantor,
    defaclnamespace::regnamespace AS schema,
    defaclobjtype AS object_type,
    defaclacl AS privileges
FROM pg_default_acl
WHERE defaclnamespace = 'analytics'::regnamespace;

-- Expected output should include:
-- grantor: (current role or postgres)
-- schema: analytics
-- object_type: r (tables/relations)
-- privileges: analytics_reader=r/... (r = SELECT)


-- ============================================================================
-- STEP 5: Set Role-Level Performance and Safety Settings
-- ============================================================================
-- These settings apply to all connections using analytics_reader role

-- Statement timeout: Kill queries running longer than 30 seconds
-- Prevents runaway queries from consuming resources
ALTER ROLE analytics_reader SET statement_timeout = '30s';

-- Idle in transaction timeout: Close connections idle in transaction > 15 seconds
-- Prevents long-held locks from blocking other operations
ALTER ROLE analytics_reader SET idle_in_transaction_session_timeout = '15s';

-- Lock timeout: Fail queries waiting for locks longer than 5 seconds
-- Prevents queries from blocking indefinitely on materialized view refreshes
ALTER ROLE analytics_reader SET lock_timeout = '5s';

-- Read-only enforcement (extra safety layer)
-- Ensures role cannot perform write operations even if grants somehow misconfigured
ALTER ROLE analytics_reader SET default_transaction_read_only = ON;

-- Connection idle timeout: Close inactive connections after 10 minutes
-- Helps free up connection slots
ALTER ROLE analytics_reader SET idle_session_timeout = '10min';

-- Verify role settings
SELECT
    rolname,
    rolconfig
FROM pg_roles
WHERE rolname = 'analytics_reader';

-- Expected rolconfig array should contain:
-- statement_timeout=30s
-- idle_in_transaction_session_timeout=15s
-- lock_timeout=5s
-- default_transaction_read_only=on
-- idle_session_timeout=10min


-- ============================================================================
-- STEP 6: Security Verification Checklist
-- ============================================================================

-- 6.1: Verify NO access to base tables
SELECT
    has_table_privilege('analytics_reader', 'public.applications', 'SELECT') as can_read_applications,
    has_table_privilege('analytics_reader', 'public.users', 'SELECT') as can_read_users,
    has_table_privilege('analytics_reader', 'public.jobs', 'SELECT') as can_read_jobs;

-- Expected: All should be 'f' (false)
-- If any are 't' (true), IMMEDIATELY run:
--   REVOKE SELECT ON TABLE public.applications FROM analytics_reader;
--   (repeat for other affected tables)


-- 6.2: Verify NO access to pgcrypto functions (encryption)
SELECT
    has_function_privilege('analytics_reader', 'pgp_sym_encrypt(text, text)', 'EXECUTE') as can_encrypt,
    has_function_privilege('analytics_reader', 'pgp_sym_decrypt(bytea, text)', 'EXECUTE') as can_decrypt;

-- Expected: Both should be 'f' (false)
-- If 't' (true), contact DBA immediately - critical security issue


-- 6.3: Verify CAN access analytics objects
SELECT
    has_table_privilege('analytics_reader', 'analytics.mv_applications', 'SELECT') as can_read_mv_applications;

-- Expected: 't' (true)
-- If 'f' (false), re-run STEP 3 grants


-- 6.4: Verify NO superuser privileges
SELECT
    rolsuper as is_superuser,
    rolcreaterole as can_create_roles,
    rolcreatedb as can_create_databases
FROM pg_roles
WHERE rolname = 'analytics_reader';

-- Expected: All should be 'f' (false)
-- If any are 't' (true), IMMEDIATELY run:
--   ALTER ROLE analytics_reader NOSUPERUSER NOCREATEROLE NOCREATEDB;


-- 6.5: Test read-only enforcement
-- Run this as analytics_reader (should fail):
--   SET ROLE analytics_reader;
--   CREATE TABLE analytics.test_write (id INT);  -- Should ERROR
--   INSERT INTO analytics.mv_applications (id) VALUES ('test');  -- Should ERROR
--   RESET ROLE;


-- ============================================================================
-- STEP 7: Connection Security (Network Level)
-- ============================================================================

-- RECOMMENDATION: Restrict analytics_reader connections via pg_hba.conf
-- Add entries like:

-- # Allow analytics_reader only from data warehouse IPs (example)
-- host    restailor    analytics_reader    10.0.5.0/24          scram-sha-256
-- host    restailor    analytics_reader    10.0.6.0/24          scram-sha-256
--
-- # Deny all other analytics_reader connections
-- host    restailor    analytics_reader    0.0.0.0/0            reject

-- ALTERNATIVE: Use connection pooler/proxy (e.g., PgBouncer, AWS RDS Proxy)
-- Configure proxy to:
--   - Limit analytics_reader to read replica (if available)
--   - Enforce TLS/SSL connections
--   - Log all queries for audit trail
--   - Rate limit connections per IP

-- SSL/TLS Enforcement (add to postgresql.conf or pg_hba.conf):
--   ssl = on
--   ssl_cert_file = '/path/to/server.crt'
--   ssl_key_file = '/path/to/server.key'
--
-- In pg_hba.conf, require SSL for analytics_reader:
--   hostssl  restailor  analytics_reader  0.0.0.0/0  scram-sha-256


-- ============================================================================
-- STEP 8: Password Rotation Procedure
-- ============================================================================

-- Run quarterly or after suspected credential leak:

-- 8.1: Generate new strong password (32+ chars, use password manager)

-- 8.2: Update password
ALTER ROLE analytics_reader PASSWORD '<new-strong-password>';

-- 8.3: Update credentials in secrets manager
--   - Doppler: Update ANALYTICS_READER_PASSWORD secret
--   - AWS Secrets Manager: Update analytics-reader-credentials secret
--   - Notify all consumers of credential rotation

-- 8.4: Monitor connections
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    query_start
FROM pg_stat_activity
WHERE usename = 'analytics_reader'
ORDER BY query_start DESC;

-- 8.5: After confirming all consumers updated, optionally:
--   - Terminate stale connections: SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'analytics_reader';


-- ============================================================================
-- STEP 9: Monitoring Queries
-- ============================================================================

-- 9.1: Check active analytics_reader connections
SELECT
    COUNT(*) as active_connections,
    MAX(query_start) as last_query_time
FROM pg_stat_activity
WHERE usename = 'analytics_reader'
  AND state = 'active';


-- 9.2: Check for long-running queries (should be rare due to statement_timeout)
SELECT
    pid,
    client_addr,
    state,
    query_start,
    NOW() - query_start AS duration,
    LEFT(query, 100) AS query_snippet
FROM pg_stat_activity
WHERE usename = 'analytics_reader'
  AND state = 'active'
  AND NOW() - query_start > INTERVAL '10 seconds'
ORDER BY duration DESC;


-- 9.3: Review query patterns (requires pg_stat_statements extension)
SELECT
    LEFT(query, 80) AS query_snippet,
    calls,
    mean_exec_time,
    max_exec_time,
    total_exec_time
FROM pg_stat_statements
WHERE usename = 'analytics_reader'
ORDER BY total_exec_time DESC
LIMIT 20;


-- ============================================================================
-- STEP 10: Revocation Procedure (Emergency)
-- ============================================================================

-- If analytics_reader credentials compromised or role no longer needed:

-- 10.1: Revoke all privileges immediately
REVOKE ALL PRIVILEGES ON SCHEMA analytics FROM analytics_reader;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA analytics FROM analytics_reader;

-- 10.2: Terminate all active connections
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'analytics_reader';

-- 10.3: Disable login
ALTER ROLE analytics_reader NOLOGIN;

-- 10.4: (Optional) Drop role entirely if no longer needed
-- WARNING: Ensure no dependencies first
DROP ROLE IF EXISTS analytics_reader;

-- 10.5: Notify all stakeholders via email/Slack


-- ============================================================================
-- APPENDIX: Common Issues and Solutions
-- ============================================================================

/*
ISSUE: analytics_reader can't connect (authentication failed)
SOLUTION:
  - Verify password is correct (check secrets manager)
  - Check pg_hba.conf allows connection from client IP
  - Verify CONNECTION LIMIT not exceeded (check pg_stat_activity)
  - Ensure SSL/TLS configured correctly if required

ISSUE: Permission denied on analytics.mv_applications
SOLUTION:
  - Re-run STEP 3 grants
  - Verify analytics schema exists: SELECT schema_name FROM information_schema.schemata;
  - Check materialized view exists: SELECT matviewname FROM pg_matviews WHERE schemaname = 'analytics';

ISSUE: Query timeout errors
SOLUTION:
  - Optimize query (add indexes, use LIMIT, avoid full table scans)
  - Increase statement_timeout if justified: ALTER ROLE analytics_reader SET statement_timeout = '60s';
  - Use read replica to reduce load on primary

ISSUE: Connection limit exceeded (5 max)
SOLUTION:
  - Implement connection pooling on client side
  - Close idle connections: SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename = 'analytics_reader' AND state = 'idle';
  - Increase limit if justified: ALTER ROLE analytics_reader CONNECTION LIMIT 10;

ISSUE: Lock timeout errors
SOLUTION:
  - Query ran during materialized view refresh (normal, retry in 1-2 seconds)
  - If persistent, check for long-held locks: SELECT * FROM pg_locks WHERE NOT granted;
*/


-- ============================================================================
-- END OF RUNBOOK
-- ============================================================================

-- Final verification command (run after completing all steps):
SELECT
    'analytics_reader setup complete' AS status,
    has_schema_privilege('analytics_reader', 'analytics', 'USAGE') AS has_analytics_access,
    has_schema_privilege('analytics_reader', 'public', 'USAGE') AS has_public_access,
    (SELECT rolconfig FROM pg_roles WHERE rolname = 'analytics_reader') AS role_config
WHERE
    has_schema_privilege('analytics_reader', 'analytics', 'USAGE') = TRUE
    AND has_schema_privilege('analytics_reader', 'public', 'USAGE') = FALSE;

-- Expected output:
-- status: "analytics_reader setup complete"
-- has_analytics_access: t (true)
-- has_public_access: f (false)
-- role_config: {statement_timeout=30s, idle_in_transaction_session_timeout=15s, ...}

-- If query returns no rows, review and re-run failed steps above.
