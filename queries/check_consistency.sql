-- Consistency Check: Single Source of Truth Verification
-- Run this to verify applications table matches expected state

-- =============================================================================
-- 1. Applications vs Analytics Snapshot Comparison
-- =============================================================================
\echo '================================================'
\echo '1. APPLICATIONS vs ANALYTICS COMPARISON'
\echo '================================================'

-- Applications aggregates
SELECT 'APPLICATIONS TABLE' as source,
       user_id,
       COUNT(*) as total,
       SUM(CAST(is_applied AS INT)) as applied,
       SUM(CAST(is_interviewing AS INT)) as interviewing,
       SUM(CAST(is_offer AS INT)) as offer,
       SUM(CAST(is_hired AS INT)) as hired
FROM public.applications
WHERE COALESCE(is_test, FALSE) = FALSE
GROUP BY user_id
ORDER BY user_id;

-- Analytics snapshot aggregates  
SELECT 'ANALYTICS SNAPSHOT' as source,
       user_id,
       COUNT(*) as total,
       SUM(CAST(is_applied AS INT)) as applied,
       SUM(CAST(is_interviewing AS INT)) as interviewing,
       SUM(CAST(is_offer AS INT)) as offer,
       SUM(CAST(is_hired AS INT)) as hired
FROM public.analytics_job_snapshot_state
WHERE is_active = TRUE
  AND COALESCE(is_test, FALSE) = FALSE
GROUP BY user_id
ORDER BY user_id;

\echo ''
\echo 'These two queries should return identical results.'
\echo ''

-- =============================================================================
-- 2. Count Mismatches Between Applications and Analytics
-- =============================================================================
\echo '================================================'
\echo '2. MISMATCH COUNT'
\echo '================================================'

WITH app_dedup AS (
    SELECT DISTINCT ON (user_id, jd_hash)
        id,
        user_id,
        jd_hash,
        is_applied,
        is_interviewing,
        is_offer,
        is_hired
    FROM public.applications
    WHERE COALESCE(is_test, FALSE) = FALSE
    ORDER BY user_id, jd_hash, created_at DESC, id DESC
)
SELECT COUNT(*) as mismatches
FROM app_dedup a
LEFT JOIN public.analytics_job_snapshot_state s ON s.snapshot_id = a.id
WHERE s.is_active = TRUE
  AND (
    COALESCE(a.is_hired, FALSE) != COALESCE(s.is_hired, FALSE)
    OR COALESCE(a.is_offer, FALSE) != COALESCE(s.is_offer, FALSE)
    OR COALESCE(a.is_interviewing, FALSE) != COALESCE(s.is_interviewing, FALSE)
  );

\echo ''
\echo 'Result should be 0 or very small number.'
\echo ''

-- =============================================================================
-- 3. Applications vs Jobs Comparison (shows where sync is needed)
-- =============================================================================
\echo '================================================'
\echo '3. APPLICATIONS vs JOBS FLAG DIFFERENCES'
\echo '================================================'

SELECT 
    a.id,
    a.user_id,
    a.jd_hash,
    a.applied_key,
    'APP: ' || COALESCE(a.is_interviewing::text, 'NULL') || 
    ' JOB: ' || COALESCE(j.is_interviewing::text, 'NULL') as interviewing_diff,
    'APP: ' || COALESCE(a.is_offer::text, 'NULL') || 
    ' JOB: ' || COALESCE(j.is_offer::text, 'NULL') as offer_diff,
    'APP: ' || COALESCE(a.is_hired::text, 'NULL') || 
    ' JOB: ' || COALESCE(j.is_hired::text, 'NULL') as hired_diff
FROM public.applications a
LEFT JOIN public.jobs j ON j.id = a.job_id
WHERE a.job_id IS NOT NULL
  AND j.deleted_at IS NULL
  AND COALESCE(a.is_test, FALSE) = FALSE
  AND (
    COALESCE(a.is_hired, FALSE) != COALESCE(j.is_hired, FALSE)
    OR COALESCE(a.is_offer, FALSE) != COALESCE(j.is_offer, FALSE)
    OR COALESCE(a.is_interviewing, FALSE) != COALESCE(j.is_interviewing, FALSE)
  )
LIMIT 10;

\echo ''
\echo 'After migration, this should return 0 rows (or very few).'
\echo ''

-- =============================================================================
-- 4. Flag Saturation Check (monotonic property)
-- =============================================================================
\echo '================================================'
\echo '4. FLAG SATURATION VIOLATIONS'
\echo '================================================'

SELECT 
    COUNT(*) as violations,
    'hired=T but offer=F' as violation_type
FROM public.applications
WHERE is_hired = TRUE 
  AND is_offer != TRUE
  AND COALESCE(is_test, FALSE) = FALSE

UNION ALL

SELECT 
    COUNT(*) as violations,
    'hired=T but interviewing=F' as violation_type
FROM public.applications
WHERE is_hired = TRUE 
  AND is_interviewing != TRUE
  AND COALESCE(is_test, FALSE) = FALSE

UNION ALL

SELECT 
    COUNT(*) as violations,
    'offer=T but interviewing=F' as violation_type
FROM public.applications
WHERE is_offer = TRUE 
  AND is_interviewing != TRUE
  AND COALESCE(is_test, FALSE) = FALSE;

\echo ''
\echo 'All counts should be 0. Saturation ensures hired→offer→interviewing.'
\echo ''

-- =============================================================================
-- 5. Per-User Summary
-- =============================================================================
\echo '================================================'
\echo '5. PER-USER SUMMARY'
\echo '================================================'

WITH app_latest AS (
    SELECT DISTINCT ON (user_id, jd_hash)
        user_id,
        is_applied,
        is_interviewing,
        is_offer,
        is_hired,
        job_id
    FROM public.applications
    WHERE COALESCE(is_test, FALSE) = FALSE
    ORDER BY user_id, jd_hash, created_at DESC, id DESC
)
SELECT 
    user_id,
    COUNT(*) as unique_jobs,
    COUNT(CASE WHEN job_id IS NOT NULL THEN 1 END) as linked_to_jobs,
    SUM(CAST(is_applied AS INT)) as applied,
    SUM(CAST(is_interviewing AS INT)) as interviewing,
    SUM(CAST(is_offer AS INT)) as offer,
    SUM(CAST(is_hired AS INT)) as hired
FROM app_latest
GROUP BY user_id
ORDER BY user_id;

\echo ''
\echo 'Summary of deduplicated applications per user.'
\echo ''

-- =============================================================================
-- 6. Sample Data (First 5 Applications)
-- =============================================================================
\echo '================================================'
\echo '6. SAMPLE APPLICATION DATA'
\echo '================================================'

SELECT 
    id,
    user_id,
    SUBSTRING(jd_hash, 1, 12) || '...' as jd_hash_short,
    is_applied as A,
    is_interviewing as I,
    is_offer as O,
    is_hired as H,
    CASE WHEN job_id IS NOT NULL THEN 'Y' ELSE 'N' END as has_job,
    created_at::date
FROM public.applications
WHERE COALESCE(is_test, FALSE) = FALSE
ORDER BY created_at DESC
LIMIT 5;

\echo ''
\echo 'Sample of most recent applications.'
\echo ''

-- =============================================================================
-- 7. Overall Health Score
-- =============================================================================
\echo '================================================'
\echo '7. OVERALL HEALTH SCORE'
\echo '================================================'

WITH metrics AS (
    SELECT 
        (SELECT COUNT(*) FROM (
            SELECT user_id, COUNT(*) as c1
            FROM public.applications
            WHERE COALESCE(is_test, FALSE) = FALSE
            GROUP BY user_id
        ) a1) as app_user_count,
        
        (SELECT COUNT(*) FROM (
            SELECT user_id, COUNT(*) as c2
            FROM public.analytics_job_snapshot_state
            WHERE is_active = TRUE AND COALESCE(is_test, FALSE) = FALSE
            GROUP BY user_id
        ) a2) as snap_user_count,
        
        (SELECT COUNT(*) 
         FROM public.applications a
         LEFT JOIN public.analytics_job_snapshot_state s ON s.snapshot_id = a.id
         WHERE s.is_active = TRUE
           AND COALESCE(a.is_test, FALSE) = FALSE
           AND (
             COALESCE(a.is_hired, FALSE) != COALESCE(s.is_hired, FALSE)
             OR COALESCE(a.is_offer, FALSE) != COALESCE(s.is_offer, FALSE)
           )
        ) as mismatches,
        
        (SELECT COUNT(*)
         FROM public.applications
         WHERE is_hired = TRUE 
           AND (is_offer != TRUE OR is_interviewing != TRUE)
           AND COALESCE(is_test, FALSE) = FALSE
        ) as saturation_violations
)
SELECT 
    CASE 
        WHEN app_user_count = snap_user_count 
             AND mismatches = 0 
             AND saturation_violations = 0 
        THEN '✓ HEALTHY'
        ELSE '✗ NEEDS ATTENTION'
    END as status,
    app_user_count,
    snap_user_count,
    mismatches,
    saturation_violations
FROM metrics;

\echo ''
\echo '✓ HEALTHY = Single source of truth is working correctly'
\echo '✗ NEEDS ATTENTION = Migration needed or sync not working'
\echo ''
\echo '================================================'
\echo 'CONSISTENCY CHECK COMPLETE'
\echo '================================================'
