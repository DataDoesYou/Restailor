# Free BYOK-Only Restailor Plan

## Summary

Convert Restailor from paid platform-key usage to free, BYOK-only usage. Billing becomes Budget, Stripe is disabled end to end, users can self-adjust budget credits with preset add/remove buttons, pricing multiplier is fixed to `1`, and all normal user model execution must require a user-supplied provider key. Platform LLM keys must never be used for normal user runs.

Primary boundaries: FastAPI routes, worker/runtime streaming, Next frontend pages/routes, user key storage, credit ledger/accounting, pricing config, docs/help, and tests.

## Phase 1: Budget, Pricing, and Stripe Disablement

- Rename the user-facing `/billing` page to `/budget`.
  - Add `frontend/app/budget/page.tsx` using the current Billing page data model and rename the client component/copy to Budget.
  - Keep `/billing` as a redirect or compatibility page to `/budget` so old bookmarks and existing links do not break.
  - Update sidebar, auth guards, help text, insufficient-balance messages, and user-facing purchase wording to say Budget.
  - Keep backend compatibility for existing consumers of `/billing/summary`; add `/budget/summary` as the canonical alias, but do not break current frontend code paths that still call `/billing/summary` during the refactor.
- Keep the Budget page transparent to normal users.
  - Show current balance, personal/global averages, and the full per-token provider price map to all authenticated normal users.
  - Hide only the multiplier from the UI because it is meaningless in free BYOK mode.
  - Do not force Budget into a narrower container if pricing/average tables need more horizontal room.
- Disable Stripe completely for user flows.
  - Remove purchase checkout behavior from the UI.
  - Make `/billing/purchase-intent` and any new Budget purchase route return a disabled response, not a checkout session.
  - Keep `/webhooks/stripe` inert when Stripe is disabled and update tests accordingly.
  - Keep or remove admin/testing credit simulation intentionally: it must not be reachable as a normal-user purchase path.
- Add self-service Budget controls.
  - Reuse preset amounts: `$5`, `$10`, `$25`, `$50`, `$100`.
  - Add two button groups: Add and Remove.
  - Backend endpoint: `POST /budget/credits/adjust` with `{ amount_usd, direction }`.
  - Validate amount against the preset allowlist, require auth, clamp balance at zero on remove, and write `CreditLedger` rows with `type="budget_adjustment"` and provider refs like `budget:self:<user_id>:<uuid>`.
  - Return fresh balance and dispatch the same frontend balance refresh event the sidebar already consumes.
- Set pricing multiplier to `1`.
  - Change `config/app.toml` pricing multiplier to `1`.
  - Harden `services.pricing.load_price_map()` so user-facing pricing and charge recording resolve multiplier as `1` in BYOK-only mode.
  - Keep provider cost tables visible because they are still useful for budget estimates, model choice, and transparency.
  - Keep charge recording, but charges should represent provider-cost-equivalent budget usage, not platform markup.

## Phase 2: BYOK Storage and Settings UI

- Add a dedicated BYOK storage surface instead of storing raw keys in generic user settings.
  - Add a `user_provider_keys` table with `user_id`, canonical provider, encrypted key bytes, masked key tail, storage mode metadata, timestamps, and a uniqueness constraint on `(user_id, provider)`.
  - Encrypt server-synced keys with the existing pgcrypto/PII-key pattern. Never return raw keys from any API.
  - Add an Alembic migration and ORM model for the table.
- Add authenticated provider-key APIs.
  - `GET /users/me/provider-keys`: returns only metadata: `{ provider, configured, key_tail, updated_at, storage_mode }`.
  - `PUT /users/me/provider-keys/{provider}`: validates provider, stores encrypted key for server sync, and returns metadata only.
  - `DELETE /users/me/provider-keys/{provider}`: removes the server-synced key and returns updated metadata.
  - Optional key test endpoint may make a provider call, but must never log or return the raw key.
- Add BYOK provider key management on Settings.
  - Providers: OpenAI, Anthropic, Gemini, xAI, matching current provider support.
  - Each provider row shows key status, masked tail only, save/test/remove controls, and a `Sync to server` toggle.
  - `Sync to server = on`: save encrypted server-side keys through the provider-key API.
  - `Sync to server = off`: store keys encrypted in client-side storage using Web Crypto AES-GCM. The local encryption key is generated per browser and stored as a non-extractable IndexedDB CryptoKey; the app can decrypt locally in that browser only.
  - Switching from server sync to local-only deletes the server key only after local encrypted save succeeds.
- Match the existing app theme.
  - Use the app's current dark slate theme, spacing, border treatment, input styling, button classes, checkbox/toggle patterns, and inline saved/error states.
  - Do not introduce a separate visual system, new color palette, marketing-style cards, oversized hero text, gradients, or custom button treatment.
  - Build BYOK controls as compact settings rows/sections that visually match the current Settings page: slate borders, transparent inputs, amber checkbox accents, muted helper text, and the same disabled/loading affordances already used there.
- Normalize secondary page widths where this work touches them.
  - Use `max-w-4xl` for Settings, Help, and Admin page content so forms, tables, and BYOK provider rows have consistent breathing room.
  - Help already uses `max-w-4xl`; update Settings from `max-w-xl` and Admin from `max-w-3xl`.
  - Preserve the current `mx-auto px-4 md:px-0` alignment and mobile padding pattern.

## Phase 3: Runtime BYOK Enforcement

- Remove platform-key fallback from all normal user model execution.
  - Update `services.llm.stream_model()` to accept an explicit API key or resolved credential object.
  - Remove env/keyring fallback from normal user calls to `stream_model`.
  - Add a strict BYOK resolver used by `/jobs`, `/fit`, `/judge`, `/benchmark/start`, `/jobs/{job_id}/tokens`, worker execution, and `/streams/test`.
  - Resolver order: job-scoped local BYOK secret, then encrypted server-synced user key.
  - Forbidden fallback: `OPENAI_API_KEY`, `CLAUDE_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`, `XAI_API_KEY`, keyring, platform config, or any Next route server environment key.
- Remove the Next `/api/streams` platform-key path.
  - Delete or rewrite `frontend/app/api/streams/route.ts` key resolution so it never reads env vars or keytar for user model execution.
  - If the route remains, it must proxy to the same FastAPI BYOK resolver and return `missing_byok_key` when the user has no key.
- Support local-only keys without leaking secrets.
  - Frontend decrypts local-only keys locally and sends them only over authenticated HTTPS to a short-lived runtime-secret endpoint before starting a model run.
  - Add `POST /byok/runtime-secrets` or an equivalent job-scoped endpoint that accepts `{ provider, key, intended_use }`, authenticates the user, stores the secret in Redis or an in-memory test fallback with a short TTL, and returns an opaque `runtime_secret_id`.
  - Do not put API keys in URLs, query strings, EventSource URLs, logs, errors, Redis keys, Postgres rows, analytics rows, or debug payloads.
  - Job creation and token-stream requests pass only the opaque `runtime_secret_id`; worker/live stream code resolves it for the matching user, provider, job/use, and expiry.
  - Delete or expire runtime secrets after completion, failure, cancellation, logout where practical, and TTL expiry.
- Enforce clear error behavior.
  - If no usable BYOK key exists for the selected provider, return `missing_byok_key` before a job is enqueued or provider call starts.
  - The Resume Tailor UI should show a concise action message pointing the user to Settings/BYOK.
  - Do not silently fall back to a cheaper/default provider, a platform key, or mock mode outside explicit test configuration.

## Phase 4: Docs, Help, and Product Copy

- Update user-facing help and page copy for free BYOK-only mode.
  - Remove paid-credit, Stripe, purchase, and premium-unlock language from Help and Budget.
  - Explain Budget as a local usage-control/accounting tool, not money paid to Restailor.
  - Explain that users need their own provider API key to run models.
  - Keep per-token provider pricing visible as transparency for budget planning.
- Update setup/operator docs.
  - Remove Stripe from normal setup instructions or mark it as deprecated/inert.
  - Keep platform provider env vars documented only if they remain for explicit admin/test utilities, and clearly state they are not used for normal user execution.

## Tests

- Backend:
  - Budget add/remove validates preset amounts, clamps at zero, writes ledger rows, and refreshes balance.
  - `/budget/summary` and existing `/billing/summary` compatibility return visible price-map and average data without exposing multiplier in UI-specific responses.
  - Stripe purchase intent and webhook are disabled/inert for normal user flows.
  - Pricing multiplier resolves to `1` for estimates and charge recording.
  - Server-synced BYOK stores encrypted bytes and only returns masked metadata.
  - Provider-key delete removes the server credential and subsequent runs fail unless a local runtime secret is supplied.
  - Missing BYOK key blocks `/jobs`, `/fit`, `/judge`, benchmark starts, token streams, worker execution, `/streams/test`, and any retained Next stream proxy.
  - Platform env/keyring/keytar keys are ignored for normal user execution even when present.
  - Local-only runtime secret is user/provider/job-use scoped, TTL-bound, not persisted, not logged, and rejected for wrong user, wrong provider, expired token, or reused invalid context.
- Frontend:
  - Sidebar shows Budget, not Billing.
  - `/billing` redirects to `/budget`.
  - Budget page add/remove buttons update balance and sidebar.
  - Budget page remains fully visible to normal users, including per-token input/output pricing and average-cost tables.
  - Multiplier is not displayed anywhere in the Budget UI.
  - Settings, Help, and Admin use consistent `max-w-4xl` content width while preserving existing alignment and mobile padding.
  - Settings BYOK rows match the current Settings page theme exactly and show saved/missing/error states without layout shift.
  - Budget buttons reuse the existing app button appearance and interaction states.
  - Sync toggle transitions preserve/delete keys according to the selected mode.
  - Model run with no key surfaces a clear Settings/BYOK action message.
- Security/logging:
  - Tests or grep checks prove raw provider keys are not returned in API responses, written to Postgres, placed in URLs, or emitted in logs/debug payloads.
  - Tests prove normal user execution cannot use platform keys even when platform env vars are configured.

## Assumptions

- Budget credits remain as a usage-control/accounting system even though users are not paying Restailor.
- Provider price tables remain visible for transparency, but multiplier/markup is hidden and fixed to `1`.
- Local-only BYOK is browser-local, not portable across devices.
- Server-synced BYOK is encrypted at rest and usable across devices after login.
- Platform provider keys may still exist for explicit admin/test utilities, but normal user model execution must never resolve or use them.
