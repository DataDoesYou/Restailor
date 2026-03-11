# API Contracts

Request/response schemas for core endpoints. See `main.py` for authoritative definitions.

CHANGE SNAPSHOT (2025-09-07)
- Added explicit docs for role-specific submit shortcuts: POST /tailor/submit, /fit, /judge.
- Clarified step-up header and cookie names (`X-Stepup-Token`, `rt_stepup`).
- Noted capability token header names (`X-Job-Token`, `X-Client-Id`).
- Minor wording/consistency fixes.

CHANGE SNAPSHOT (2025-09-11)
- Documented benchmark endpoints (/benchmark/start, /benchmark/rank, /benchmark/save, /benchmark/await_and_judge).
- Clarified job_flow enumerations: tailor | fit | judge | benchmark | benchmark_rank.
- Added notes on multi-model judge & benchmark ranking deriving charges.model_count.

## Endpoint summary

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | /health | none | basic liveness |
| GET | /healthz | none | ok, db, redis |
| GET | /time | none | server time |
| POST | /signup | none | create user |
| POST | /token | none | get JWT |
| POST | /logout | cookie | clears session |
| POST | /jobs | bearer + X-Client-Id | generic job submit (all roles) |
| POST | /tailor/submit | bearer + X-Client-Id | shortcut: job_flow=tailor |
| POST | /fit | bearer + X-Client-Id | shortcut: job_flow=fit |
| POST | /judge | bearer + X-Client-Id | shortcut: job_flow=judge (single-model) |
| GET | /jobs/{id}/status | bearer | owner-only |
| POST | /jobs/{id}/cancel | bearer | cancel if running |
| GET | /jobs/{id}/result | bearer + X-Job-Token | artifact text |
| DELETE | /jobs/{id} | bearer | delete job |
| GET | /jobs/{id}/stream | bearer + X-Job-Token | SSE progress/chunks/final |
| POST | /benchmark/start | admin + bearer | creates container job (job_flow=benchmark) |
| POST | /benchmark/rank | bearer | enqueue ranking of candidate models (job_flow=benchmark_rank) |
| POST | /benchmark/save | bearer + X-Job-Token | persist benchmark markdown snapshot |
| POST | /benchmark/await_and_judge | bearer | convenience: wait for rank then judge |
| POST | /auth/stepup/start | bearer | TOTP / recovery / email OTP |
| POST | /auth/stepup/webauthn/options | bearer | start step-up via WebAuthn |
| POST | /auth/stepup/webauthn/verify | bearer | issues step-up ticket (header/cookie) |
| POST | /webauthn/register/options | bearer | passkeys register |
| POST | /webauthn/register/verify | bearer | persist credential |
| POST | /webauthn/authenticate/options | pending_2fa token | passkeys auth start |
| POST | /webauthn/authenticate/verify | pending_2fa token | returns access token |
| GET | /webauthn/credentials | bearer | list creds |
| PATCH | /webauthn/credentials/{id} | bearer | update nickname |
| DELETE | /webauthn/credentials/{id} | bearer | delete cred |
| GET | /pricing/estimate | none | price quote |
| GET | /pricing/averages | bearer | recent averages |
| GET | /pricing/median | none | median of last 100 |
| GET | /pricing/average | none | trimmed average |
| GET | /users/me/balance | bearer | user balance |
| GET | /billing/summary | bearer | balance + rates + averages |

## Admin Credits

Requires admin role. Some endpoints also require a recent step-up token.

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | /admin/credits/gift | admin + step-up | credit a single user by id or email |
| POST | /admin/credits/gift-bulk | admin + step-up | credit many users; supports dry_run and idempotency_prefix |
| POST | /admin/credits/reverse | admin + step-up | reverse a prior positive ledger entry by id |
| GET | /admin/credits/balance | admin | get balance by user_id or email |
| GET | /admin/credits/ledger | admin | list recent ledger rows for a user |
| POST | /admin/credits/sim-purchase | admin + step-up | simulate a purchase (local/testing) |
| POST | /admin/credits/sim-refund | admin + step-up | simulate a refund (local/testing) |

Notes
- Bulk gift enforces idempotency via provider_ref per row; use idempotency_prefix to stabilize keys.
- Balance and ledger endpoints are read-only but still restricted to admin role.


## Health

- GET /healthz
  - Response: { ok: boolean, db?: "ok|down|skip|unknown", redis?: "ok|down|skip|unknown" }
- GET /time
  - Response: { iso: string }

## Auth (subset)

- POST /signup → Creates user; returns { ok: true } or error
- POST /token → Returns { access_token: string, token_type: "bearer" }
- POST /logout → { ok: true }

## Jobs

- POST /jobs
  - Body: { resume_text: string, jd_text: string, provider?: string, model_id?: string, do_judge?: boolean, judge_provider?: string, judge_model_id?: string, source_page?: string }
  - Headers: Idempotency-Key?; X-Run-Id?; Authorization: Bearer ...
  - Response: { job_id: string, access_token: string }

Job flows (job_flow field / request_type for billing)
- tailor (single model tailor)
- fit (candidate fit analysis)
- judge (single model judge)
- benchmark (container coordinating ranking & judging)
- benchmark_rank (ranking multi-model candidates)


- POST /tailor/submit | /fit | /judge
  - Body: same shape as POST /jobs but inferred `job_flow` based on path shortcut.
  - Purpose: ergonomic role-specific endpoints (identical auth & response contract).

- GET /jobs/{job_id}/status
  - Headers: Authorization: Bearer ...
  - Response: { state: string, progress?: number, bytes?: number, updated_at?: string }

- POST /jobs/{job_id}/cancel
  - Headers: Authorization: Bearer ...
  - Response: { job_id: string, status: "cancelling" }

- GET /jobs/{job_id}/result
  - Headers: X-Job-Token: string (capability), Authorization: Bearer ...
  - Response: { job_id: string, state: string, artifact?: string }

- DELETE /jobs/{job_id}
  - Headers: Authorization: Bearer ...
  - Response: 204 No Content

- GET /jobs/{job_id}/stream
  - SSE stream; include X-Job-Token header; events: progress/chunk/final

### Benchmark endpoints (multi-model ranking & judging)

See also `Benchmark.md` for deep dive.

- POST /benchmark/start (admin)
  - Body: { source_page?: string }
  - Creates a container job (job_flow=benchmark) returning { job_id, access_token }.
  - Use returned job_id & access_token for subsequent benchmark actions.
- POST /benchmark/rank
  - Body: { job_id: string, candidates: [ { provider: string, model_id: string, prompt?: string } ... ], judge?: { provider, model_id }, source_page?: string }
  - Kicks off multi-model ranking (job_flow=benchmark_rank). Each candidate run contributes to `charges.model_count`.
  - Response: { job_id, access_token } referencing a ranking job.
- POST /benchmark/save
  - Headers: X-Job-Token (from original /benchmark/start)
  - Body: { job_id: string, bench_md: string, raw_md?: string }
  - Persists markdown snapshot as a job_output row.
- POST /benchmark/await_and_judge
  - Body: { run_id: string, timeout_sec?: int }
  - Waits for rank job completion then triggers judge phase, returning composite status/result metadata.

Charging notes
- `charges.model_count` counts distinct model inferences for a ranked judge batch.
- Benchmark container jobs themselves may be zero-cost; ranking & judge phases incur normal token-based pricing.
- Pre-enqueue insufficient funds returns 402 `insufficient_funds` (no job created) using pricing estimate.

## WebAuthn

- POST /webauthn/register/options → { publicKey }
- POST /webauthn/register/verify { credential, nickname? } → { ok: true }
- POST /webauthn/authenticate/options (Authorization: pending_2fa token) → { publicKey }
- POST /webauthn/authenticate/verify { credential, remember_device? } → { ok, access_token, token_type }
- GET /webauthn/credentials → [ { id, credential_id, nickname?, created_at, transports?, aaguid?, sign_count } ]
- PATCH /webauthn/credentials/{id} { nickname? } → updated record
- DELETE /webauthn/credentials/{id} → 204

## Step-up (reauth)

- POST /auth/stepup/start { totp_code?, recovery_code?, email_otp_code? } → { ok: true, ttl_seconds }
- POST /auth/stepup/webauthn/options → { publicKey }
- POST /auth/stepup/webauthn/verify { credential } → { ok: true, ttl_seconds }

Headers/Cookies
- Step-up ticket returned client-side must be echoed via header `X-Stepup-Token` (preferred) or cookie `rt_stepup` to satisfy admin-protected endpoints (TTL default 300s; configurable via `[security.stepup].ttl_seconds` or env override).
  - Failure shape for missing/expired token: 403 { "detail": "needs_stepup" }
  - Test bypass: During pytest runs most endpoints skip step-up unless `REQUIRE_STEPUP=1` and in targeted admin step-up test module.

---

## Pricing

- GET /pricing/estimate
  - Query: request_type, model, expected_prompt_tokens, expected_completion_tokens
  - 200: { estimate_cents: int, estimate_usd: string, currency: string }
  - 400: { detail: "unknown_model" }

- GET /pricing/averages
  - Query: scope=global|user, model?, request_type?
  - 200: [{ request_type, model, avg_price_usd, n }] or { request_type: { avg_price_usd, n } }

- GET /pricing/median and /pricing/average
  - 200: { median_price_usd or average_price_usd, n, free_requests_for_one_dollar, excluded_types }

- GET /users/me/balance
  - 200: { balance_cents, balance_usd, currency }

- GET /billing/summary
  - 200: { balance, multiplier, price_map, averages_by_model, averages_global }

## Pricing Configuration

- Pricing is sourced from TOML config only:
  - [pricing] for multiplier/currency
  - [pricing.models] for input/output rates
  - [pricing.aliases] for display-name aliases

- GET /admin/token_billing_stats
  - Auth: Authorization: Bearer <admin>, X-Stepup-Token: <ticket>
  - 200: { total_charges, charges_with_real_tokens, charges_with_estimates_only, charges_with_partial_real, real_token_percentage, avg_estimation_error_pct, total_undercharge_usd, total_overcharge_usd, undercharge_count, overcharge_count }
  - Returns comprehensive statistics on billing accuracy (real vs estimated tokens)

See Pricing.md for calculation details and TOKEN_BILLING.md for billing methodology.

## Applications & History

- GET /applications/list
  - Query: page, page_size, search?, show_applied_only?, archived?, sort_by?, sort_dir?, stage_filter?
  - Returns paginated list of applications with hydrated job data, stage flags, and analytics info.
  - Response: { items: [...], total, page, page_size, total_pages }
  
- GET /applications/{id}
  - Returns single application with full job details.
  
- POST /applications/{id}/stage
  - Body: { stage: "applied" | "interviewing" | "offer" | "hired" }
  - Updates stage flags for application (cascades to linked job).
  
- DELETE /applications/{id}
  - Soft-deletes application.

## Analytics

- GET /analytics/funnel
  - Returns stage counts: applied, interviewing, offer, hired.
  - Query: time_range?, user_id? (admin only)
  
- GET /analytics/trends
  - Returns time-series data for application stages.
  - Query: period?, metric?
  
- POST /analytics/rebuild
  - Admin only: triggers full analytics snapshot rebuild.
  - Returns: { ok: true, rebuilt_count: int }

---

CHANGELOG
- 2025-10-03: Added applications & analytics endpoint documentation reflecting Single Source of Truth architecture.
- 2025-09-15: Added X-Client-Id requirement, 402 insufficient_funds note, test bypass mention.
- 2025-09-11: Added benchmark endpoints & job_flow enumeration; expanded multi-model pricing notes.
- 2025-09-07: Added /tailor/submit, /fit, /judge, clarified step-up headers & cookies, capability tokens.
- 2025-09-04: Documented admin credits API endpoints.
- 2025-09-02: Initial API contracts for health, jobs, WebAuthn, and step-up.
- 2025-09-02: Added pricing, billing, and admin pricing endpoints.
