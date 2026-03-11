SELECT id,
       status,
       created_at,
       updated_at,
       input_hash,
       latency_ms,
       resume_enc,
       jd_enc,
       candidate_enc,
       job_flow,
       source_page,
       access_token,
       client_id,
       user_id,
       is_test
FROM public.jobs
--where job_flow = 'tailor+judge'
order by created_at desc
LIMIT 1000


delete from public.jobs where request_type = 'queued'
delete from public.jobs where job_flow = 'tailor+judge'
delete from public.charges where charges.request_type  = 'tailor+judge'

SELECT * from jobs where source_page like '%Test%'

DELETE FROM jobs where source_page like '%Test%'

SELECT id, stage, has_applied, has_interviewing, has_offer, has_hired, updated_at
FROM public.jobs
WHERE user_id = 4
ORDER BY updated_at DESC;