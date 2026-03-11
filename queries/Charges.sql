SELECT *
FROM public.charges
where prompt_tokens > 0 and completion_tokens > 0
LIMIT 1000;

SELECT *
FROM public.charges
--where request_type = 'judge'
order by created_at desc
LIMIT 1000;

SELECT avg(price_to_user_usd) as avg_usd, request_type, model, model_count
FROM public.charges
where prompt_tokens > 0 and completion_tokens > 0
group by request_type, model, model_count
order by request_type, model, model_count

SELECT created_at
    ,request_type
    ,model
    ,prompt_tokens
    ,completion_tokens
    ,prompt_tokens_real
    ,completion_tokens_real
    ,reasoning_tokens_real
FROM public.charges
--where request_type = 'judge'
order by created_at desc
LIMIT 1000;

delete from public.users where id > 4

select * from public.users