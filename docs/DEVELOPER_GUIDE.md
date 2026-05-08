# Restailor Developer Guide

This guide gets you from clone to a running development stack quickly. It covers local setup, environment, health checks, and common day-to-day commands.

New to the project? Start with [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) for the broader architecture and product context.

## Documentation Index

### Getting Started
- [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - This file: local setup and daily development workflow
- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) - High-level project overview and tech stack

### Architecture And API
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design, data flow, and key patterns
- [API.md](API.md) - REST API reference
- [DB.md](DB.md) - Database schema, migrations, and data model

### Testing And Operations
- [TESTS.md](TESTS.md) - Testing strategy and conventions
- [ANALYTICS.md](ANALYTICS.md) - Analytics engine and funnel tracking
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guidance

### Maintenance Notes
- Model upgrades are documented in this guide under model lifecycle and deprecations

### Archive
- [archive/](archive/) - Historical docs and implementation notes

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Poetry
- Node 18+
- Doppler CLI optional but recommended

### 1. Clone And Configure

```powershell
git clone https://github.com/DataDoesYou/Restailor.git
cd restailor
cp .env.example .env
```

Edit `.env` with the required secrets and at least one provider key for live model calls.

If you use Doppler, either pass the project/config explicitly:

```bash
doppler run --project restailor --config dev -- docker compose -f docker/docker-compose.dev.yml up --build
```

Or bind the current checkout once so later `doppler run -- ...` commands work from this folder:

```bash
doppler setup --project restailor --config dev
```

### 2. Start Infrastructure

```bash
doppler run --project restailor --config dev -- docker compose -f docker/docker-compose.dev.yml up -d postgres redis

# Or without Doppler:
docker compose -f docker/docker-compose.dev.yml up -d postgres redis
```

The Docker dev stack uses the default local ports:

- Frontend: http://localhost:3000
- API: http://localhost:8000
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

If another local stack is running, stop it first or override the host ports:

```bash
POSTGRES_HOST_PORT=15432 REDIS_HOST_PORT=16379 API_HOST_PORT=8001 NEXT_HOST_PORT=3001 \
  doppler run --project restailor --config dev -- docker compose -f docker/docker-compose.dev.yml up --build
```

The frontend public API and site URLs follow `API_HOST_PORT` and `NEXT_HOST_PORT` unless explicitly overridden.

The default Postgres volume preserves existing local data from the previous project name. Docker may warn that `resume-tailor_pgdata` was created by the old project name; that warning is expected when reusing the existing local database. Set `POSTGRES_VOLUME_NAME` only if you intentionally want another local database volume.

The API container runs without Uvicorn reload in Docker because WSL can expose a package symlink loop under `frontend/node_modules`. Restart the API container after backend code changes.

### 3. Install Dependencies

```powershell
# Backend
poetry install

# Frontend
cd frontend
npm install
cd ..
```

### 4. Run Migrations

```bash
doppler run --project restailor --config dev -- poetry run alembic upgrade head

# Or without Doppler:
poetry run alembic upgrade head
```

### 5. Start Services

Terminal 1, API:

```bash
doppler run --project restailor --config dev -- poetry run uvicorn main:app --reload --port 8000

# Or without Doppler:
poetry run uvicorn main:app --reload --port 8000
```

Terminal 2, worker:

```bash
doppler run --project restailor --config dev -- poetry run arq worker.WorkerSettings

# Or without Doppler:
poetry run arq worker.WorkerSettings
```

Terminal 3, frontend:

```powershell
cd frontend
npm run dev
```

### 6. Verify

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Deep health: http://localhost:8000/healthz

## Health Checks

```powershell
# API health
curl http://localhost:8000/health

# Deep health (database and Redis)
curl http://localhost:8000/healthz

# Database check
docker exec restailor-postgres-1 pg_isready

# Redis check
docker exec restailor-redis-1 redis-cli ping
```

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

## Environment Variables

Key values live in `.env`, with the full template in `.env.example`.

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/restailor

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
AUTH_SECRET_KEY=your-256-bit-secret
VERIFY_SECRET_KEY=your-256-bit-secret

# AI providers
OPENAI_API_KEY=sk-...
CLAUDE_API_KEY=sk-ant-...

# Email (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=your@email.com
MAIL_PASSWORD=app-password

# Feature flags
STRIPE_ENABLED=false
WEBAUTHN_ENABLED=true
```

## Common Issues

### Docker

```powershell
# View logs
docker compose -f docker/docker-compose.dev.yml logs -f

# Restart services
docker compose -f docker/docker-compose.dev.yml restart

# Clean restart
docker compose -f docker/docker-compose.dev.yml down
docker compose -f docker/docker-compose.dev.yml up -d
```

### Database Reset

```powershell
# Destructive reset
docker compose -f docker/docker-compose.dev.yml down -v
docker compose -f docker/docker-compose.dev.yml up -d postgres
poetry run alembic upgrade head
```

### Port Conflicts

```powershell
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux or macOS
lsof -i :8000
kill -9 <PID>
```

### Session Persistence And Refresh

Auth uses a short-lived access token and a long-lived refresh token.

- `rt_session` expires after 60 minutes.
- `rt_refresh` persists for 30 days to support transparent session recovery.
- Both are `HttpOnly`, so frontend code cannot inspect them directly.

If a user returns after the access token expires, the frontend should still attempt `/auth/refresh` after a `401` from `/users/me`. The prior bug was caused by a frontend heuristic that assumed the user was anonymous once a short-lived local storage marker expired, which suppressed the refresh attempt even though the refresh cookie was still valid.

The expected behavior is:

1. `/users/me` returns `401` after an expired access token.
2. The client attempts `/auth/refresh` regardless of that stale heuristic.
3. A valid refresh cookie issues new tokens.
4. The client retries `/users/me` and restores the session transparently.

### Model Lifecycle And Deprecations

The model upgrade system automatically migrates saved user selections away from deprecated models when those models are removed from the configured allowlist.

- No database rewrite is required.
- Original model IDs remain stored.
- Upgrades happen during validation and API response shaping.
- The system prefers a replacement from the same provider before falling back to the system default.

The upgrade order is:

1. Keep the model as-is if it is still allowed.
2. Apply an explicit mapping from `get_model_upgrade_map()` if one exists.
3. Fall back to the default model for the same provider.
4. Fall back to the system default tailor model.

In practice this means you can usually update `config/app.toml`, remove the retired model, add the replacement, and deploy. Users with older saved selections will transparently receive a valid replacement model in API responses and the frontend.

If you need a specific migration path instead of the default same-provider fallback, define it in `restailor/settings_schemas.py`:

```python
def get_model_upgrade_map() -> dict[str, str]:
	return {
		"openai:gpt-4.1": "openai:gpt-5.1-instant",
		"gpt-4.1": "gpt-5.1-instant",
	}
```

Validation points:

- `ModelSettings.validate_against_allowlist()` applies the upgrade logic.
- Upgraded values are returned by the API.
- The stored database value is preserved for backward compatibility.

Recommended verification after changing model config:

1. Call `/users/me/model-settings` for a user with a deprecated saved model and confirm the response shows the replacement.
2. Verify the sidebar auto-selects the replacement model.
3. Submit a job and confirm billing and job records reflect the replacement model.

## Next Steps

1. Read [ARCHITECTURE.md](ARCHITECTURE.md).
2. Review [API.md](API.md).
3. Inspect [DB.md](DB.md).
4. Follow [TESTS.md](TESTS.md) before adding or changing behavior.
5. Use [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.

## Additional Resources

- [archive/](archive/) - Historical documentation and older setup notes
