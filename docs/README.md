# Resume Tailor – Developer Onboarding

This guide gets you from clone to a running stack in under 30 minutes. It covers local setup, environment, health checks, and common dev commands.

**🆕 New to the project?** Start with [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) for a comprehensive introduction.

---

## 📖 Documentation Index

### Getting Started
- **[README.md](README.md)** - This file: 30-minute quick start guide
- **[PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md)** - Complete project overview with tech stack

### Architecture & API
- **[architecture.md](architecture.md)** - System design, data flow, and patterns
- **[API.md](API.md)** - Complete REST API endpoint reference
- **[DB.md](DB.md)** - Database schema, migrations, and data model

### Testing & Operations
- **[Tests.md](Tests.md)** - Testing strategy, patterns, and best practices
- **[Analytics.md](Analytics.md)** - Analytics engine and funnel tracking
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide (includes Stripe, Cloudflare, Render setup)

### Troubleshooting
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and debugging

### Archive
- **[archive/](archive/)** - Historical docs and implementation notes

---

## Quick Start

### Prerequisites

**Windows, Linux, or macOS** with:

- Docker & Docker Compose
- Python 3.10+ with Poetry
- Node 18+
- Doppler CLI (optional, but recommended)

---

## 30-Minute Quick Start

### 1. Clone & Configure

```powershell
git clone https://github.com/DataDoesYou/Restailor.git
cd restailor

# Copy example environment
cp .env.example .env

# Edit .env with your API keys
```

---

### 2. Start Infrastructure

```powershell
# Start PostgreSQL and Redis
doppler run -- docker compose -f docker/docker-compose.dev.yml up -d postgres redis

# OR without Doppler:
docker compose -f docker/docker-compose.dev.yml up -d postgres redis
```

---

### 3. Install Dependencies

```powershell
# Backend
poetry install

# Frontend
cd frontend
npm install
cd ..
```

---

### 4. Setup Database

```powershell
# Run migrations
doppler run -- poetry run alembic upgrade head

# OR without Doppler:
poetry run alembic upgrade head
```

---

### 5. Start Services

**Terminal 1 - API:**
```powershell
doppler run -- poetry run uvicorn main:app --reload --port 8000

# OR without Doppler:
poetry run uvicorn main:app --reload --port 8000
```

**Terminal 2 - Worker:**
```powershell
doppler run -- poetry run arq worker.WorkerSettings

# OR without Doppler:
poetry run arq worker.WorkerSettings
```

**Terminal 3 - Frontend:**
```powershell
cd frontend
npm run dev
```

---

### 6. Verify

Open browser to:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/healthz

---

## Health Checks

```powershell
# API health
curl http://localhost:8000/health

# Deep health (checks DB and Redis)
curl http://localhost:8000/healthz

# Database check
docker exec restailor-postgres-1 pg_isready

# Redis check
docker exec restailor-redis-1 redis-cli ping
```

---

## Development Commands

### Backend

```powershell
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov

# Format code
poetry run black .
poetry run isort .

# Lint
poetry run flake8
poetry run mypy .

# Type check
poetry run mypy restailor/

# Security scan
poetry run bandit -r restailor/
```

### Frontend

```powershell
cd frontend

# Run tests
npm test

# Build
npm run build

# Lint
npm run lint

# Type check
npm run type-check
```

### Database

```powershell
# Create new migration
poetry run alembic revision --autogenerate -m "description"

# Upgrade to latest
poetry run alembic upgrade head

# Downgrade one revision
poetry run alembic downgrade -1

# Show current revision
poetry run alembic current

# Show migration history
poetry run alembic history
```

---

## Environment Variables

Key variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/restailor

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
AUTH_SECRET_KEY=your-256-bit-secret
VERIFY_SECRET_KEY=your-256-bit-secret

# AI Providers (at least one required)
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...

# Email (optional for dev)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your@email.com
MAIL_PASSWORD=app-password

# Feature Flags
STRIPE_ENABLED=false  # Set to true to enable payments
WEBAUTHN_ENABLED=true  # Passkey authentication
```

See `.env.example` for the complete list.

---

## Troubleshooting

### Docker Issues

```powershell
# View logs
docker compose -f docker/docker-compose.dev.yml logs -f

# Restart services
docker compose -f docker/docker-compose.dev.yml restart

# Clean restart
docker compose -f docker/docker-compose.dev.yml down
docker compose -f docker/docker-compose.dev.yml up -d
```

### Database Issues

```powershell
# Reset database (DESTRUCTIVE)
docker compose -f docker/docker-compose.dev.yml down -v
docker compose -f docker/docker-compose.dev.yml up -d postgres
poetry run alembic upgrade head
```

### Port Conflicts

```powershell
# Find process using port 8000
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/Mac

# Kill process
taskkill /PID <PID> /F  # Windows
kill -9 <PID>  # Linux/Mac
```

**For detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).**

---

## Next Steps

1. **Learn the architecture:** [architecture.md](architecture.md)
2. **Explore the API:** [API.md](API.md)
3. **Understand the database:** [DB.md](DB.md)
4. **Write tests:** [Tests.md](Tests.md)
5. **Deploy to production:** [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Additional Resources

- [archive/setup/](archive/setup/) - Archived detailed setup guides for third-party services

---

## Quick Start
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and debugging

**� Additional Resources**
- [setup/](setup/) - Detailed setup guides for third-party services
- [archive/](archive/) - Historical documentation

Recent highlights (2025-10-03)
- **Single Source of Truth**: Applications table now stores all stage flags (is_applied, is_interviewing, is_offer, is_hired) with cascading updates from jobs table.
- **Analytics Snapshot State**: `analytics_job_snapshot_state` table tracks active job snapshots with unified stage resolution via `stage_utils.py`.
- **Job Hash Hints**: Applications table includes `job_input_hashes` JSONB column for efficient history hydration without redundant decrypts.
- **History & Analytics API**: `/applications/list` and `/analytics/*` endpoints provide consistent job tracking and funnel analytics.
- **Multi-model Support**: Benchmark endpoints support ranking multiple LLM candidates with model_count tracking.
- **Enhanced Security**: WebAuthn (passkeys), TOTP 2FA, trusted devices, step-up authentication for admin actions.
- **Comprehensive Testing**: Mandatory test script ensures Postgres schema with all migrations applied.

## Quick start

- Prereqs
  - Windows 10/11, WSL optional
  - Docker Desktop
  - Python 3.10–3.13
  - Poetry >= 1.7
  - Node 18+ (recommended 20+)

- Clone and bootstrap

```powershell
# Clone
git clone https://github.com/DataDoesYou/Restailor.git
cd restailor

# Copy env template and adjust values
Copy-Item .\.env.example .\.env

# Bring up Postgres + Redis (dev compose)
# Note the compose file path
docker compose -f docker/docker-compose.dev.yml up -d postgres redis

# Install backend deps
poetry install

# Apply DB migrations (creates schema, enables pgcrypto)
poetry run alembic upgrade head

# Install frontend deps
cd .\frontend
npm install
cd ..
```

- Run services (three terminals)

```powershell
# 1) API
poetry run uvicorn main:app --host localhost --port 8000
```

```powershell
# 2) Worker
poetry run arq worker.WorkerSettings
```

```powershell
# 3) Frontend
cd .\frontend
npm run dev
```

Optional one-runner (root): `npm run dev` will start API, worker, and frontend together using concurrently.

Shortcut submit
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/tailor/submit -Headers @{ Authorization = "Bearer $token" } -Body (@{ resume_text = "..."; jd_text = "..." } | ConvertTo-Json) -ContentType 'application/json'
```

- Smoke checks

```powershell
# API health
Invoke-RestMethod http://localhost:8000/health    # shallow
Invoke-RestMethod http://localhost:8000/healthz   # deep

# Time endpoint
Invoke-RestMethod http://localhost:8000/time
```

If these return JSON and the frontend is on http://localhost:3000, the stack is up.

## Key Features

**AI-Powered Resume Tailoring**
- Tailor resumes to specific job descriptions
- Multi-model support (OpenAI, Claude, Gemini, Grok)
- Real-time streaming with progress tracking
- Benchmark mode for comparing multiple models

**Job Application Tracking**
- Centralized history dashboard
- Stage tracking: Applied → Interviewing → Offer → Hired
- Smart deduplication by job description
- Optimistic UI updates with conflict resolution

**Analytics & Insights**
- Conversion funnel visualization
- Trend analysis over time
- Active vs. archived job filtering
- Real-time metrics

**Security & Privacy**
- WebAuthn (passkeys) + TOTP 2FA
- PII encryption at rest (pgcrypto)
- Privacy opt-out controls
- Trusted device management
- Step-up authentication for admin actions

**Pricing & Credits**
- Token-based transparent pricing
- Balance tracking with cents precision
- Admin credit management (gift, bulk, reverse)
- Cost estimates before job submission

See [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) for comprehensive details.

## Pricing overview

- Public estimate: GET /pricing/estimate → returns cents and formatted USD.
- Recent averages: GET /pricing/averages, /pricing/median, /pricing/average.
- Balance and effective rates: GET /billing/summary, GET /users/me/balance.
- Source of truth: pricing is loaded from [pricing] and [pricing.models] in config/app.toml.

See Pricing.md for formulas, config, and examples.

## Canonical .env.example

Place this at repo root as .env (copy from the block or use .env.example). Do not commit secrets.

```dotenv
# --- Core app secrets ---
# Required. Use a strong, random string or set in OS keyring service='restailor' username='AUTH_SECRET_KEY'.
AUTH_SECRET_KEY=dev-insecure-secret-change-me
# Optional but recommended. Separate signing keys for email verify/reset tokens.
VERIFY_SECRET_KEY=
RESET_SECRET_KEY=
# Required. Used by pgcrypto to encrypt PII in Postgres at rest (or set in keyring service='restailor-app' username='pii_encryption_key').
PII_ENCRYPTION_KEY=local-dev-pgp-key-change-me
# 2FA: Fernet key to encrypt TOTP secrets (urlsafe base64, 32-byte key)
TOTP_FERNET_KEY=REPLACE_WITH_URLSAFE_BASE64_FERNET_KEY
# Trusted devices cookie signer
SECURITY_REMEMBER_SIGNER_SECRET=replace-with-long-random
## Admin-only API key for protected maintenance endpoints (optional)
ADMIN_API_KEY=

# --- Database ---
# EITHER provide DATABASE_URL OR parts below. docker-compose uses POSTGRES_PASSWORD.
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/restailor
# For Compose dev, these are used by the postgres container:
POSTGRES_USER=postgres
POSTGRES_DB=restailor
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
DB_NAME=restailor
POSTGRES_PASSWORD=postgres

# --- Redis (queues, ephemeral state) ---
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# --- Email / SMTP (optional) ---
MAIL_SERVER=localhost
MAIL_PORT=1025
MAIL_FROM=noreply@example.test
MAIL_STARTTLS=0
MAIL_SSL_TLS=0
MAIL_USE_CREDENTIALS=0
MAIL_USERNAME=
MAIL_PASSWORD=

# --- CAPTCHA (optional for dev) ---
TURNSTILE_SECRET_KEY=
# Public site key used by the frontend login/signup CAPTCHA
NEXT_PUBLIC_TURNSTILE_SITE_KEY=

# --- Providers (optional for mock mode; required for live model calls) ---
OPENAI_API_KEY=
CLAUDE_API_KEY=
GEMINI_API_KEY=
GROK_API_KEY=

# --- WebAuthn (passkeys) ---
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=Resume Tailor
WEBAUTHN_ORIGIN=http://localhost:3000

# --- Feature flags / hardening ---
# In dev, keep STRICT_SECRETS=0; in prod set 1 to require explicit secrets.
STRICT_SECRETS=0
FEATURE_CANCEL_V2=1
REQUIRE_ADMIN_2FA=0
COOKIE_SECURE=0

# --- Performance knobs (optional) ---
PROVIDER_TIMEOUT_S=600
```

## Secrets management (Doppler)

You can optionally centralize secrets with Doppler instead of relying only on local keyring + `.env`.

Layer precedence (highest first) at runtime:
1. Process env (injected by `doppler run` or your platform)
2. OS keyring (if value not in env)
3. `.env` file (loaded on startup for dev)
4. `config/app.toml` defaults

Local workflow (PowerShell):
```powershell
# Login once
doppler login

# Set active config (example dev project)
doppler setup

# Run API with secrets
doppler run -- poetry run uvicorn main:app --host localhost --port 8000

# Compose stack with injected secrets
doppler run -- docker compose -f docker/docker-compose.dev.yml up --build
```

Populate Doppler with the same keys shown in the `.env.example` (avoid committing real values). For binary / long secrets, let Doppler generate and copy to production. Keys that must be explicit in STRICT mode: `AUTH_SECRET_KEY`, `PII_ENCRYPTION_KEY`, `TOTP_FERNET_KEY`, `SECURITY_REMEMBER_SIGNER_SECRET`, provider API keys.

Fallbacks: If a secret is absent in Doppler/env and STRICT_SECRETS=0, the app may issue warnings and continue (dev only). In production set `STRICT_SECRETS=1` so missing secrets fail fast.

### Env vars (critical subset)

| Name | Purpose | Source (prod) | Dev default |
|------|---------|---------------|-------------|
| AUTH_SECRET_KEY | JWT signing key | Keyring or env | dev-insecure-secret-change-me |
| VERIFY_SECRET_KEY | Email verification token signing (falls back to AUTH if unset) | Keyring or env | (inherits AUTH) |
| PII_ENCRYPTION_KEY | pgcrypto symmetric key | Keyring or env | required in dev |
| TOTP_FERNET_KEY | Encrypt TOTP secrets | Keyring or env | required in dev |
| SECURITY_REMEMBER_SIGNER_SECRET | Sign trusted-device cookies | Keyring or env | required in dev |
| DATABASE_URL / DB_* | Postgres connection | Env (managed) | docker compose defaults |
| REDIS_HOST/PORT/DB | Redis connection | Env (managed) | 127.0.0.1:6379/0 |
| WEBAUTHN_* | Passkeys RP config | Env or app.toml | localhost / http://localhost:3000 |
| STRICT_SECRETS | Enforce secrets | Env | 0 (dev), 1 (prod) |

Notes
- For local dev you can keep STRICT_SECRETS=0 to allow safe fallbacks; production must set 1 and supply all secrets.
- When using Docker Desktop, the provided compose exposes Postgres 5432 and Redis 6379.
- See `docs/Input-Gating.md` for required `X-Client-Id` and optional `Idempotency-Key` headers on job submissions.
- See `docs/Privacy.md` for `dont_save_future_data` persistence opt-out behavior.

## Health checks

- GET /health → { ok: true }
- GET /healthz → { ok: true, db?, redis? }
- GET /time → server time isoformat
- GET /__captcha/ready → readiness for CAPTCHA token cache

```powershell
Invoke-RestMethod http://localhost:8000/healthz
```

## Common dev commands

```powershell
# Run unit/integration tests
poetry run pytest -q

# Lint (ruff) – optional
poetry run ruff check .

# Format (black)
poetry run black .

# Apply migrations
poetry run alembic upgrade head

# Create new migration (autogenerate)
poetry run alembic revision --autogenerate -m "change description"
```

## Deployment runbook (minimum viable)

Checklist
- Backing services: Postgres 16, Redis 7
- Secrets: provide via environment or platform secret manager (see Security.md)
- Migrations: run Alembic upgrade head on each deploy

Steps

```powershell
# 1) Set secrets and config as environment variables
# 2) Provision Postgres and Redis
# 3) Run migrations
poetry run alembic upgrade head

# 4) Start API (as a service)
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2

# 5) Start worker
poetry run arq worker.WorkerSettings
```

Rollback
- Deploys are stateless; rollback by redeploying previous commit. Use down migrations only if strictly necessary.

## Troubleshooting

- API fails at startup: "Secret validation failed"
  - Set STRICT_SECRETS=0 in dev or provide AUTH_SECRET_KEY and MFA secrets via env or keyring.
- Postgres connection error
  - Ensure docker compose is running; verify DATABASE_URL or DB_* vars; check pg_hba.conf for remote.
- Alembic migration fails on pgcrypto
  - Ensure your Postgres user can CREATE EXTENSION; run as superuser locally.
- Worker cannot connect to Redis
  - Start Redis (docker compose). In tests, the API degrades gracefully without Redis.
- 401 on authenticated endpoints
  - Obtain token via POST /token; include Authorization: Bearer <token>.
- 403 admin endpoint
  - User must have role=admin and (by default) 2FA confirmed.

---

## Additional Documentation

- [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) - **NEW!** Comprehensive project overview
- [QUICK-REFERENCE.md](QUICK-REFERENCE.md) - **NEW!** Quick reference for common commands
- [architecture.md](architecture.md) - Updated with Single Source of Truth architecture
- [API.md](API.md) - Updated with applications & analytics endpoints
- [DB.md](DB.md) - Updated schema with stage flags and hash hints
- [Security.md](Security.md) - Updated with data protection details
- [Tests.md](Tests.md) - Updated with current test coverage
- [Repo.md](Repo.md) - Updated module listing and endpoints

CHANGELOG
- 2025-10-03: **Major documentation update** - Created PROJECT-OVERVIEW.md and QUICK-REFERENCE.md, updated all core docs to reflect Single Source of Truth architecture, applications/analytics system, and current state of the project.
- 2025-09-15: Added input gating + privacy docs and VERIFY_SECRET_KEY env var.
- 2025-09-11: Added benchmark endpoints & multi-model pricing notes.
- 2025-09-07: Added Doppler secrets management section.
- 2025-09-07: Added submit shortcuts, step-up header/cookie note, abuse/ASN policy pointer.
- 2025-09-04: Clarified Docker dev compose path, health endpoints, and env template keys (POSTGRES_*).
- 2025-09-02: Initial comprehensive README with quickstart, canonical .env.example, runbook, and troubleshooting.

## Docker Dev

This repo uses a single dev-focused Docker compose to run Postgres, Redis, FastAPI, ARQ worker, and Next.js with hot reload.

Prerequisites
- Docker Desktop (Windows/macOS) or Docker Engine (Linux)

First run

```powershell
# With Doppler-managed secrets (recommended for dev):
doppler run -- docker compose -f docker/docker-compose.dev.yml up --build

# Or plain Docker Compose using your local .env:
docker compose -f docker/docker-compose.dev.yml up --build
```

Services and URLs
- API (FastAPI with reload): http://localhost:8000
  - Health: http://localhost:8000/health (liveness), http://localhost:8000/healthz (deep)
- Frontend (Next.js dev): http://localhost:3000
  - Health: http://localhost:3000/api/health
- Postgres: localhost:5432 (mapped from container)
- Redis: localhost:6379 (mapped from container)

Shut down

```powershell
docker compose -f docker/docker-compose.dev.yml down
```

Clean volumes (dangerous: deletes Postgres data)

```powershell
docker compose -f docker/docker-compose.dev.yml down -v
```

Rebuild images without cache

```powershell
docker compose -f docker/docker-compose.dev.yml build --no-cache
```

Tail logs

```powershell
docker compose -f docker/docker-compose.dev.yml logs -f
```

Environment
- Copy `.env.example` to `.env` at repo root to override defaults for dev. Only include non-secret overrides in `.env`; keep real secrets in your local environment or a secret store.

Troubleshooting tips
- Bind mounts on Windows: If code changes don't reflect, ensure file sharing is enabled in Docker Desktop and the workspace is on a shared drive.
- Frontend node_modules: The Next.js service uses an anonymous volume for `/app/node_modules`. If you change Node versions, rebuild (build without cache).
- File watchers: Some environments limit inotify watchers. If reload seems flaky, try increasing watchers on Linux or restarting containers.
- Ports in use: If a port is occupied, stop the other process or adjust published ports in `docker/docker-compose.dev.yml`.

### Production notes (image-based)

- A `docker-compose.prod.yml` is provided for image-based runs without bind mounts. It builds images for API, ARQ, and Next.js.
- Set `NEXT_PUBLIC_API_BASE_URL` to your real API base (e.g., https://api.example.com) for the frontend at build/run time. For server-side calls from inside Docker, use `INTERNAL_API_BASE_URL`.
- Use a secrets manager or platform environment for sensitive values (AUTH_SECRET_KEY, PII_ENCRYPTION_KEY, TOTP_FERNET_KEY, SECURITY_REMEMBER_SIGNER_SECRET, DATABASE_URL, REDIS_URL). Avoid committing secrets to the repo.
- Postgres/Redis are typically external in prod—leave them commented out or point `DATABASE_URL`/`REDIS_URL` to managed services.
- Uvicorn in prod runs without `--reload`. Adjust workers/timeout via your process manager or orchestrator.

---

## Contributing

### Branch Naming
- **Features:** `feat/<scope>` (e.g., `feat/analytics-export`)
- **Fixes:** `fix/<scope>` (e.g., `fix/auth-timeout`)
- **Chores:** `chore/<scope>` (e.g., `chore/update-deps`)

### Commit Messages
Follow conventional commits:
```
feat(scope): add new feature
fix(scope): fix bug
docs(scope): update documentation
test(scope): add tests
chore(scope): update dependencies
```

### Code Style
- **Python:** Type hints, docstrings for public functions, max line length 120, PEP 8 (enforced by Ruff + Black)
- **TypeScript:** Strict mode, functional components, use types not `any`, Airbnb style guide

### Testing
All code changes must include tests (unit, integration, or E2E for critical flows).

**Before submitting PR:**
```powershell
# Backend tests
doppler run -- pwsh -File scripts/run_tests_local.ps1

# Frontend tests
cd frontend
npm run test && npm run test:e2e
```

### Migrations
When adding database changes:
1. Create: `poetry run alembic revision --autogenerate -m "description"`
2. Review generated SQL carefully
3. Add indexes for new hot queries
4. Test upgrade AND downgrade
5. Update DB.md if schema changed

### Release Hygiene
- Test on staging before production
- Document changes (README, Security.md, API.md as needed)
- Monitor logs after deployment

### Production notes (image-based)

- A `docker-compose.prod.yml` is provided for image-based runs without bind mounts. It builds images for API, ARQ, and Next.js.
- Set `NEXT_PUBLIC_API_BASE_URL` to your real API base (e.g., https://api.example.com) for the frontend at build/run time. For server-side calls from inside Docker, use `INTERNAL_API_BASE_URL`.
- Use a secrets manager or platform environment for sensitive values (AUTH_SECRET_KEY, PII_ENCRYPTION_KEY, TOTP_FERNET_KEY, SECURITY_REMEMBER_SIGNER_SECRET, DATABASE_URL, REDIS_URL). Avoid committing secrets to the repo.
- Postgres/Redis are typically external in prod—leave them commented out or point `DATABASE_URL`/`REDIS_URL` to managed services.
- Uvicorn in prod runs without `--reload`. Adjust workers/timeout via your process manager or orchestrator.

