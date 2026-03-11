SELECT user_id,
       balance_cents,
       updated_at,
       is_test,
       created_at
FROM public.user_balance
LIMIT 1000;

SELECT id,
       created_at,
       user_id,
       delta_cents,
       type,
       note,
       provider_ref,
       is_test,
       admin_id
FROM public.credit_ledger
LIMIT 1000;