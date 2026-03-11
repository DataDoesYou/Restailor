SELECT user_id,
       count(*) as snapshot_count,
       sum(cast(is_applied as int)) as is_applied,
       sum(cast(is_interviewing as int)) as is_interviewing,
       sum(cast(is_offer as int)) as is_offer,
       sum(cast(is_hired as int)) as is_hired
FROM public.applications
GROUP BY user_id
LIMIT 1000;

SELECT user_id,
       count(*) as snapshot_count,
       sum(cast(is_applied as int)) as is_applied,
       sum(cast(is_interviewing as int)) as is_interviewing,
       sum(cast(is_offer as int)) as is_offer,
       sum(cast(is_hired as int)) as is_hired
FROM public.analytics_job_snapshot_state
where is_active = true
GROUP BY user_id
LIMIT 1000;


delete from public.applications where user_id > 4
delete from public.analytics_job_snapshot_state where user_id > 4

select * from public.applications
order by jd_hash
--created_at desc

select * from public.applications
order by applied_key_canonical
--created_at desc

SELECT COUNT(*) 
FROM public.applications 
WHERE user_id = 4 
  AND COALESCE(is_test, FALSE) = FALSE;

SELECT *
FROM public.applications
LIMIT 1000

  SELECT *
FROM public.analytics_job_snapshot_state
LIMIT 1000;

WITH latest AS (
    SELECT
        a.*,
        ROW_NUMBER() OVER (
            PARTITION BY a.user_id, a.jd_hash
            ORDER BY a.created_at DESC, a.id DESC
        ) AS rn
    FROM public.applications AS a
    WHERE COALESCE(a.is_test, FALSE) = FALSE
),
dedup AS (
    SELECT
        l.*,
        j.is_interviewing AS job_is_interviewing,
        j.is_offer        AS job_is_offer,
        j.is_hired        AS job_is_hired,
        j.is_archived,
        j.deleted_at,
        j.is_test         AS job_is_test
    FROM latest AS l
    LEFT JOIN public.jobs AS j
      ON j.id = l.job_id
    WHERE l.rn = 1
),
final AS (
    SELECT
        d.*,
        (COALESCE(d.job_is_hired, d.is_hired, FALSE))                                        AS final_hired,
        (COALESCE(d.job_is_hired, d.is_hired, FALSE)
         OR COALESCE(d.job_is_offer, d.is_offer, FALSE))                                     AS final_offer,
        (COALESCE(d.job_is_hired, d.is_hired, FALSE)
         OR COALESCE(d.job_is_offer, d.is_offer, FALSE)
         OR COALESCE(d.job_is_interviewing, d.is_interviewing, FALSE))                       AS final_interviewing,
        (d.job_id IS NOT NULL
         AND COALESCE(d.job_is_test, FALSE) = FALSE
         AND COALESCE(d.is_test, FALSE) = FALSE
         AND COALESCE(d.is_archived, FALSE) = FALSE
         AND d.deleted_at IS NULL)                                                           AS is_active
    FROM dedup AS d
)
SELECT
    user_id,
    id AS snapshot_id,
    jd_hash,
    created_at,
    is_applied,
    final_interviewing,
    final_offer,
    final_hired,
    is_active,
    CASE
        WHEN is_active THEN NULL
        WHEN job_id IS NULL THEN 'no job link'
        WHEN COALESCE(job_is_test, FALSE) THEN 'job flagged test'
        WHEN COALESCE(is_test, FALSE) THEN 'application flagged test'
        WHEN COALESCE(is_archived, FALSE) THEN 'job archived'
        WHEN deleted_at IS NOT NULL THEN 'job deleted'
        ELSE 'filtered for other reason'
    END AS exclusion_reason
FROM final
ORDER BY user_id, is_active DESC, created_at DESC;