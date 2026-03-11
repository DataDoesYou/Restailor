# Resume Tailor - Project Overview

**Last Updated:** December 31, 2025

## Executive Summary

Resume Tailor is a production-grade SaaS application that uses AI to tailor resumes to specific job descriptions, analyze candidate fit, and provide job application tracking with analytics. The platform features a modern web interface, secure authentication including WebAuthn/2FA, comprehensive API, and robust background job processing.

## Tech Stack

### Backend
- **Framework:** FastAPI (Python 3.10-3.13)
- **Database:** PostgreSQL 16 with pgcrypto for PII encryption
- **Cache/Queue:** Redis 7 (ARQ worker queue)
- **ORM:** SQLAlchemy 2.0+
- **Migrations:** Alembic
- **Authentication:** JWT, TOTP 2FA, WebAuthn (passkeys), trusted devices
- **API:** RESTful with Server-Sent Events (SSE) for streaming

### Frontend
- **Framework:** Next.js 16 (React 19)
- **Styling:** TailwindCSS
- **Testing:** Playwright (E2E), Vitest (unit)
- **State Management:** React hooks with optimistic updates
- **Charts:** Recharts for analytics visualization

### Infrastructure
- **Containerization:** Docker with multi-stage builds
- **Orchestration:** Docker Compose (dev), ready for k8s (prod)
- **Secrets:** Doppler integration, OS keyring fallback
- **Monitoring:** Structured logging
- **Deployment:** Render-ready with production configs
- **Email:** SMTP via Brevo (formerly Sendinblue)

### AI Providers
- OpenAI (GPT-5.2 Instant, GPT-5.2 Thinking)
- Anthropic Claude (Opus 4.5, Sonnet 4.5)
- Google Gemini (3.0 Pro, 3.0 Flash)
- xAI Grok (Grok 4, Grok 4.1 Fast)
- Extensible provider abstraction in `services/llm.py`

## Architecture Highlights

### Single Source of Truth (Applications System)
- **Applications table** is the canonical source for all job stage flags
- Stage changes cascade from jobs → applications for consistency
- Unique constraint on `(user_id, jd_hash)` prevents duplicates
- Hash hints stored in JSONB for efficient history hydration
- Shared `stage_utils.py` ensures consistency across all endpoints

### Data Flow
```
User Action → API → Database (applications table)
                 ↓
              Redis Queue → ARQ Worker → LLM Provider
                 ↓
              Database (jobs, job_outputs, charges)
                 ↓
              SSE Stream → Frontend Update
                 ↓
              Analytics Snapshot (denormalized for performance)
```

### Security Layers
1. **Authentication:** JWT bearer tokens, OAuth2 password flow
2. **2FA/MFA:** TOTP, WebAuthn passkeys, recovery codes
3. **Step-up:** Short-lived tickets for sensitive admin actions (300s TTL)
4. **Trusted Devices:** Signed cookies with server-side validation
5. **PII Encryption:** All sensitive data encrypted at rest (pgcrypto)
6. **Rate Limiting:** SlowAPI on auth/step-up endpoints
7. **Input Gating:** Size caps, URL policy, sanitization, idempotency

## Core Features

### Resume Tailoring
- AI-powered resume optimization for specific job descriptions
- Multi-model support with benchmark ranking
- Real-time streaming output with progress tracking
- Cancellable jobs with graceful abort handling

### Candidate Fit Analysis
- Analyze how well a candidate matches a job description
- Identify strengths and gaps
- Actionable recommendations

### Judge & Ranking
- Compare multiple AI model outputs
- Automated quality assessment
- Multi-model benchmark flows with `model_count` tracking

### Job Application Tracking (History)
- Centralized dashboard of all applications
- Stage tracking: Applied → Interviewing → Offer → Hired
- Optimistic UI updates with conflict resolution
- Pagination, search, filtering, sorting

### Analytics & Insights
- Funnel visualization (conversion rates by stage)
- Trend analysis over time
- Active vs. archived job tracking
- Real-time metrics with denormalized snapshots

### Pricing & Credits
- Token-based pricing with provider-specific rates
- Configurable multipliers and model rates
- Transparent cost estimates before job submission
- Balance tracking with cents precision
- Credit ledger with full audit trail
- Admin gift/bulk/reverse operations

## Key Modules

### Backend Core
- `main.py` - FastAPI app with all route handlers (10,000+ lines)
- `worker.py` - ARQ background tasks (2,600+ lines)
- `restailor/` - Application modules
  - `models.py` - SQLAlchemy ORM models
  - `applications_api.py` - Applications CRUD and history
  - `routers/analytics.py` - Analytics endpoints
  - `stage_utils.py` - Shared stage resolution logic
  - `security.py`, `auth.py` - Authentication/authorization
  - `twofa.py`, `webauthn.py` - MFA implementations
  - `stepup.py` - Admin step-up authentication
  - `input_gate.py` - Input validation and sanitization
  - `privacy.py` - Data retention controls

### Backend Services
- `services/llm.py` - Multi-provider LLM abstraction with streaming
- `services/pricing.py` - Cost calculation and price management
- `services/credits.py` - Balance operations
- `services/admin_credits.py` - Admin credit operations
- `services/analytics_job_snapshot.py` - Snapshot rebuilds
- `services/application_sync.py` - Stage cascade logic
- `services/emailer.py` - Email notifications (verification, OTP)

### Frontend Core
- `app/` - Next.js pages and layouts
- `components/` - React components
  - `history/HistoryClient.tsx` - Application list with optimistic updates
  - `StageSegments.tsx` - Stage UI with analytics tracking
- `hooks/` - Custom React hooks
  - `useHistoryData.ts` - History state management
- `lib/` - Utility libraries
  - `api.ts` - API client
  - `stageFlags.ts` - Stage flag normalization
  - `stageAnalyticsHelpers.ts` - Debug analytics

### Backend Utilities
- `backend/hash_utils.py` - JD hashing and normalization
- `backend/crypto_utils.py` - PII encryption helpers
- `perf/observability.py` - Request/SQL timing logs

## Database Schema

### Core Tables
- `users` - User accounts with 2FA settings
- `jobs` - AI processing jobs with encrypted inputs
- `job_outputs` - Job results with encrypted content
- `applications` - **Primary source** for job tracking with stage flags
- `analytics_job_snapshot_state` - Denormalized analytics view

### Security Tables
- `webauthn_credentials` - Passkey public keys
- `user_trusted_devices` - Remember-me device tokens
- `email_otps` - Email OTP codes for verification

### Financial Tables
- `charges` - Per-job cost records with token counts
- `credit_ledger` - All credit transactions (gifts, purchases, refunds)
- `user_balance` - Current balance cache

### Audit Tables
- `email_logs` - Email delivery tracking
- `audit_events` - Security and compliance events

### Key Constraints
- Unique: `applications(user_id, jd_hash)` - one application per JD
- Unique: `applications(job_id)` - one-to-one with jobs (when linked)
- Index: JSONB `job_input_hashes` with jsonb_path_ops for efficient queries

## API Endpoints (Summary)

### Public
- `GET /health`, `/healthz`, `/time` - Health checks
- `POST /signup` - User registration
- `POST /token` - JWT authentication
- `GET /pricing/estimate` - Cost estimation

### Authenticated
- `POST /jobs`, `/tailor/submit`, `/fit`, `/judge` - Job submission
- `GET /jobs/{id}/status`, `/result`, `/stream` - Job access
- `POST /jobs/{id}/cancel` - Job cancellation
- `GET /applications/list` - Application history
- `POST /applications/{id}/stage` - Update stage
- `GET /analytics/funnel`, `/trends` - Analytics

### Admin
- `POST /admin/credits/gift` - Gift credits (requires step-up)
- `POST /admin/credits/gift-bulk` - Bulk gift (requires step-up)
- `POST /admin/credits/reverse` - Reverse ledger entry (requires step-up)
- `POST /analytics/rebuild` - Rebuild snapshots
- `POST /benchmark/start` - Create benchmark container

## Testing Strategy

### Backend Tests
- **Mandatory:** Run via `scripts/run_tests_local.ps1` (enforced by guard)
- PostgreSQL schema with all migrations applied
- Unit tests for helpers (security, 2FA, WebAuthn)
- Integration tests for job lifecycle
- E2E tests for admin flows with step-up

### Frontend Tests
- Vitest for unit/component tests
- Playwright for E2E and visual regression
- Mock API server for isolated testing
- Analytics debug tools for troubleshooting

### Coverage Areas
- Authentication (JWT, 2FA, WebAuthn, step-up)
- Job processing (submit, stream, cancel)
- Applications (CRUD, stage updates, history)
- Analytics (funnel, trends, snapshot consistency)
- Pricing (estimates, balance, credits)
- Security (encryption, rate limits, input validation)

## Configuration

### Environment Variables (required)
```bash
# Secrets (keyring or Doppler preferred)
AUTH_SECRET_KEY=...
VERIFY_SECRET_KEY=...
RESET_SECRET_KEY=...
PII_ENCRYPTION_KEY=...
TOTP_FERNET_KEY=...
SECURITY_REMEMBER_SIGNER_SECRET=...

# Database
DATABASE_URL=postgresql://...
# OR
DB_USER=postgres
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=restailor

# Redis
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0

# AI Providers
OPENAI_API_KEY=...
CLAUDE_API_KEY=...
GEMINI_API_KEY=...
```

### Config Files
- `config/app.toml` - Application defaults, limits, pricing
- `pyproject.toml` - Poetry dependencies
- `alembic.ini` - Database migration settings
- `pytest.ini` - Test configuration

## Development Workflow

### Local Setup (PowerShell)
```powershell
# 1. Clone and install dependencies
git clone https://github.com/DataDoesYou/Restailor.git
cd restailor
poetry install
cd frontend && npm install && cd ..

# 2. Start infrastructure
docker compose -f docker/docker-compose.dev.yml up -d postgres redis

# 3. Run migrations
poetry run alembic upgrade head

# 4. Start services (three terminals or use concurrently)
poetry run uvicorn main:app --reload  # API
poetry run arq worker.WorkerSettings   # Worker
cd frontend && npm run dev             # Frontend

# Or use single command:
npm run dev  # Runs all three via concurrently
```

### With Doppler
```powershell
doppler setup  # Configure project/config
doppler run -- npm run dev
```

### Running Tests
```powershell
# Backend (MANDATORY via script)
doppler run -- pwsh -File scripts/run_tests_local.ps1

# Frontend E2E
cd frontend
npm run test:e2e

# Single test file
npm run test:e2e -- ioh-button-hydration.spec.ts
```

## Production Deployment

### Build Images
```bash
docker build -f docker/api.Dockerfile --target prod -t restailor-api .
docker build -f docker/arq.Dockerfile --target prod -t restailor-worker .
docker build -f docker/next.Dockerfile --target prod -t restailor-frontend ./frontend
```

### Environment Requirements
- Set `STRICT_SECRETS=1` to fail fast on missing secrets
- Use managed PostgreSQL (16+) with pgcrypto extension
- Use managed Redis (7+) for reliability
- Configure `DATABASE_URL` and `REDIS_URL` via platform secrets
- Set all required AI provider API keys
- Configure WebAuthn `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN`

### Migrations
- Run `poetry run alembic upgrade head` before deployment
- Migrations are idempotent and can safely re-run
- Monitor `alembic_version` table for applied revisions

### Monitoring
- Health checks at `/health` (basic) and `/healthz` (deep)
- Structured logging to stdout
- Email delivery tracking in `email_logs` table
- Audit events in `audit_events` table

## Recent Major Changes

### Single Source of Truth (October 2025)
- Applications table now stores all stage flags
- Cascade updates from jobs to applications
- Unified stage resolution via `stage_utils.py`
- Hash hints for efficient history queries
- Analytics snapshot rebuilt on demand

### Migrations Applied
- `20251008_applications_job_hash_hints` - Added job_input_hashes
- `20251007_applications_stage_cleanup` - Added stage flags to applications
- `20251006_add_job_stage_columns` - Added stage flags to jobs
- `20251005_single_snapshot_per_jd` - Unique constraint enforcement
- `20251001_0900_snapshot_is_active` - Added is_active flag

### IOH Button System (September 2025)
- Optimistic UI updates with conflict resolution
- Analytics tracking for debugging
- E2E test suite (9/10 passing with mock API)
- Comprehensive debugging tools in browser console

## Documentation Index

**Complete documentation available in `/docs` folder - 18 focused documents:**

### 🚀 Start Here
- **README.md** - 30-minute onboarding guide
- **PROJECT-OVERVIEW.md** - This file: complete system overview
- **QUICK-REFERENCE.md** - Common commands and quick fixes

### 📐 Architecture
- **architecture.md** - System design, data flow, Single Source of Truth
- **API.md** - Complete API endpoint reference
- **DB.md** - Database schema, migrations, ERD
- **Repo.md** - Repository structure and key modules

### 🔐 Security & Quality
- **Security.md** - Auth, encryption, MFA, incident response
- **Tests.md** - Testing strategy and mandatory procedures
- **Privacy.md** - Data retention and privacy controls

### 💰 Features
- **Pricing.md** - Pricing calculations and credit management
- **Input-Gating.md** - Input validation and sanitization
- **Performance.md** - Optimization strategies
- **Benchmark.md** - Multi-model AI benchmarking

### 🚢 Operations
- **DEPLOYMENT.md** - Production deployment, rollback, monitoring
- **FRONTEND-UI.md** - Stage buttons, optimistic updates, analytics
- **Contributing.md** - Code style, git workflow, PR process

## Support & Maintenance

### Common Tasks

**Reset local database:**
```powershell
docker compose -f docker/docker-compose.dev.yml down -v
docker compose -f docker/docker-compose.dev.yml up -d postgres
poetry run alembic upgrade head
```

**Rebuild analytics:**
```bash
# Via API (admin + bearer token)
POST /analytics/rebuild
```

**Check migration status:**
```powershell
poetry run alembic current
poetry run alembic history
```

**Validate migrations:**
```powershell
python scripts/check_migrations.py
```

**Export analytics (browser console):**
```javascript
window.__exportStageAnalytics()
window.__analyzeStageIssues()
```

### Troubleshooting

**Tests failing:**
- Ensure using `scripts/run_tests_local.ps1` (NOT `pytest` directly)
- Check Docker Compose is running (postgres, redis)
- Verify `STRICT_SECRETS=0` for tests

**Stage buttons not updating:**
- Check browser console for `window.__analyzeStageIssues()`
- Verify WebSocket/SSE connection for live updates
- Check network tab for failed API calls

**Migration conflicts:**
- Run `python scripts/check_migrations.py`
- Check for duplicate or missing down_revision references
- Ensure revision IDs are ≤32 characters

**Pricing discrepancies:**
- Verify `config/app.toml` pricing section
- Check admin pricing overrides via API
- Review charges table for actual costs

## Pricing & Credits

**Credit System**
- Users purchase credits to use AI features
- Each operation costs credits based on model and token usage
- Real-time balance checking before job execution
- Insufficient balance returns 402 Payment Required

**Credit Pricing** (configured in `config/app.toml` `[pricing]` section)
- Default: $0.01 per credit
- Multiplier: 5.0x (configurable)
- Bulk purchase discounts available
- Admin can grant credits via `/admin/users/{id}/credits/grant`

**Operation Costs**
- Resume tailoring: Variable (depends on model and length)
- Fit analysis: Variable (depends on model and length)
- Judge/ranking: Variable × number of models
- Benchmark: Container cost (0) + ranking cost × candidate count

**Token-Based Billing**
- Input tokens: Charged at model provider rate
- Output tokens: Charged at model provider rate (typically 2-3× input rate)
- `charges` table tracks exact token usage and cost per job
- `model_count` field tracks multi-model operations

**Free Trial**
- New users receive initial credits (configurable)
- Trial gating based on IP/ASN classification (see Security.md)
- Residential/University: Full trial access
- Unknown/Datacenter: May require 2FA or payment

**Credit Management Endpoints**
- `POST /credits/purchase` - Buy credits (Stripe integration)
- `GET /credits/balance` - Check current balance
- `GET /credits/history` - Transaction history
- `POST /admin/users/{id}/credits/grant` - Admin grant (requires step-up)

**Refund Policy**
- Failed jobs automatically refund credits
- Cancelled jobs refund unused credits
- Partial completion charges proportionally

## Repository Structure

```
restailor/
├── main.py                           # FastAPI application entry point
├── worker.py                         # ARQ background worker
├── config_loader.py                  # Configuration loading with Doppler/keyring
├── config.py                         # App configuration models
├── pyproject.toml                    # Python dependencies (Poetry)
├── alembic.ini                       # Alembic migration config
├── pytest.ini                        # Pytest configuration
│
├── alembic/                          # Database migrations
│   ├── env.py                        # Migration environment
│   ├── script.py.mako                # Migration template
│   └── versions/                     # Migration files
│
├── backend/                          # Core utilities
│   ├── crypto_utils.py               # Encryption helpers
│   └── hash_utils.py                 # Hash generation
│
├── restailor/                    # Main API modules
│   ├── applications_api.py           # Job application tracking
│   ├── auth_api.py                   # Authentication endpoints
│   ├── jobs_api.py                   # Job processing endpoints
│   ├── admin_api.py                  # Admin endpoints
│   ├── analytics_api.py              # Analytics endpoints
│   ├── webauthn_api.py               # WebAuthn/passkey endpoints
│   ├── stage_utils.py                # Stage resolution helpers
│   └── models.py                     # SQLAlchemy models
│
├── services/                         # Business logic
│   ├── llm.py                        # AI provider abstraction
│   ├── analytics_job_snapshot.py     # Analytics snapshot management
│   ├── application_sync.py           # Stage cascade logic
│   ├── email_service.py              # Email sending
│   └── charge_calculator.py          # Credit/pricing logic
│
├── frontend/                         # Next.js application
│   ├── app/                          # App router pages
│   │   ├── page.tsx                  # Resume Tailor main page
│   │   ├── history/                  # Application history
│   │   ├── analytics/                # Analytics dashboard
│   │   └── admin/                    # Admin panel
│   ├── components/                   # React components
│   │   ├── pages/                    # Page-level components
│   │   ├── history/                  # History-specific components
│   │   └── ui/                       # Reusable UI components
│   ├── hooks/                        # Custom React hooks
│   │   ├── useHistoryData.ts         # History state management
│   │   └── useAuth.ts                # Authentication hook
│   ├── lib/                          # Frontend utilities
│   │   ├── apiClient.ts              # API client with auth
│   │   ├── stageFlags.ts             # Stage flag normalization
│   │   └── types.ts                  # TypeScript types
│   ├── e2e.visual/                   # Playwright E2E tests
│   └── public/                       # Static assets
│
├── tests/                            # Backend unit/integration tests
│   ├── test_auth.py                  # Auth tests
│   ├── test_applications.py          # Application tracking tests
│   ├── test_jobs.py                  # Job processing tests
│   └── conftest.py                   # Pytest fixtures
│
├── e2e/                              # Full-stack E2E tests
│   ├── playwright.config.ts          # Playwright config
│   └── tests/                        # E2E test suites
│
├── docker/                           # Docker configurations
│   ├── docker-compose.dev.yml        # Dev services (postgres, redis)
│   ├── docker-compose.prod.yml       # Production multi-container
│   ├── api.Dockerfile                # FastAPI image
│   ├── arq.Dockerfile                # Worker image
│   └── next.Dockerfile               # Next.js image
│
├── docs/                             # Documentation
│   ├── README.md                     # Quick start guide & index
│   ├── PROJECT-OVERVIEW.md           # This file
│   ├── architecture.md               # System design
│   ├── API.md                        # API reference
│   ├── DB.md                         # Database schema
│   ├── Security.md                   # Security guide
│   ├── Tests.md                      # Testing guide
│   ├── DEPLOYMENT.md                 # Deployment guide
│   ├── QUICK-REFERENCE.md            # Command reference
│   └── Contributing.md               # Contribution guide
│
├── scripts/                          # Utility scripts
│   ├── run_tests_local.ps1           # Test runner with Postgres
│   └── check_migrations.py           # Migration validator
│
├── config/                           # Configuration files
│   ├── app.toml                      # Application settings
│   └── app_settings.json             # Legacy settings
│
├── prompts/                          # AI prompt templates
│   ├── tailor.md                     # Resume tailoring prompt
│   ├── fit.md                        # Fit analysis prompt
│   └── judge.md                      # Judge/ranking prompt
│
└── queries/                          # SQL query scripts
    └── History and Analytics Check.sql
```

**Key Design Patterns**
- **Separation of Concerns**: API routes (restailor/) vs business logic (services/)
- **Dependency Injection**: Database sessions, config via FastAPI dependencies
- **Repository Pattern**: SQLAlchemy models with service layer abstraction
- **Feature Modules**: Each major feature (auth, applications, analytics) in separate file
- **Shared Utilities**: Common helpers in backend/, lib/ for DRY principle

## Contributing

See `docs/Contributing.md` for:
- Code style guidelines (Ruff, Black, Prettier)
- Git workflow (feature branches, PR requirements)
- Review process
- Security disclosure policy

## License

Proprietary - All rights reserved

---

**Project Status:** ✅ Production-ready with active development

**Last Major Release:** Single Source of Truth Architecture (October 2025)

**Next Milestones:**
- Enhanced analytics dashboards
- Additional AI provider integrations
- Mobile-responsive UI improvements
- Advanced reporting features
