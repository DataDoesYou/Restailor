# Restailor

Restailor is an open-source resume tailoring platform with a FastAPI backend, a Next.js frontend, PostgreSQL for persistence, Redis-backed background jobs, and optional LLM provider integrations.

If you want to use Restailor without setting up the OSS stack yourself, use the hosted app at [restailor.com](https://restailor.com).

The repository is structured for self-hosting and local development. Secrets are expected to come from your local environment or a secret manager such as Doppler, but the repo includes a single root `.env.example` that documents the variables needed to run the stack.

## Features

- AI-assisted resume tailoring against a job description
- Candidate fit analysis and multi-model comparison flows
- Job/application tracking with analytics endpoints and dashboards
- Background processing with ARQ workers and Redis
- Authentication with JWT, TOTP, WebAuthn, and trusted devices
- Docker-based local development for API, worker, frontend, Postgres, and Redis

## Architecture Overview

- `main.py` hosts the FastAPI application and API routes.
- `worker.py` runs ARQ background jobs for LLM and async processing.
- `restailor/` contains the core backend modules, routers, auth, models, and config loaders.
- `services/` contains business logic for LLM providers, pricing, analytics, email, and credits.
- `frontend/` contains the Next.js application.
- `docker/` contains local and production-oriented container definitions.

See `docs/architecture.md` for the detailed component view.

## Tech Stack

- Backend: Python 3.10+, FastAPI, SQLAlchemy, Alembic, ARQ
- Frontend: Next.js 16, React 19, Tailwind CSS
- Data: PostgreSQL 16, Redis 7
- Testing: Pytest, Playwright, Vitest
- Integrations: OpenAI, Anthropic, Gemini, Grok, SMTP, Stripe, WebAuthn

## Quick Start

### Prerequisites

- Python 3.10 to 3.13
- Poetry
- Node.js 18+
- Docker Desktop or Docker Engine with Compose

### Clone and Install

```bash
git clone https://github.com/DataDoesYou/Restailor.git
cd restailor
cp .env.example .env
poetry install
npm --prefix frontend install
```

### Configure Environment

Edit `.env` and set, at minimum:

- `AUTH_SECRET_KEY`
- `PII_ENCRYPTION_KEY`
- `TOTP_FERNET_KEY`
- `SECURITY_REMEMBER_SIGNER_SECRET`
- One provider key such as `OPENAI_API_KEY`

For local-only development you can keep `STRICT_SECRETS=0` and leave optional integrations blank.

### Run Locally

```bash
docker compose -f docker/docker-compose.dev.yml up -d postgres redis
poetry run alembic upgrade head
poetry run uvicorn main:app --reload --host 127.0.0.1 --port 8000
poetry run arq worker.WorkerSettings
npm --prefix frontend run dev
```

Open `http://localhost:3000` for the frontend and `http://localhost:8000/docs` for the API docs.

### Run with Docker

```bash
docker compose -f docker/docker-compose.dev.yml up --build
```

This starts Postgres, Redis, the API, the worker, and the frontend using the root `.env` file.

### Stripe Webhooks in Docker Dev

This dev stack uses `cloudflared` to expose the local API (`http://api:8000`) through your Cloudflare tunnel.
Point your Stripe webhook endpoint to that tunnel URL and keep `STRIPE_WEBHOOK_SECRET` in env/Doppler aligned with the Stripe endpoint secret.

To verify tunnel logs:

```bash
docker compose -f docker/docker-compose.dev.yml logs -f cloudflared
```

Without webhook forwarding, Checkout can succeed but credits will not be applied.

Doppler is optional. If you use Doppler, you can run the same command with injected secrets:

```bash
doppler run --project restailor --config dev -- docker compose -f docker/docker-compose.dev.yml up --build
```

If you do not use Doppler, copy `.env.example` to `.env` and use plain `docker compose`.

## Running Tests

```bash
poetry run pytest
npm --prefix frontend run test
npm --prefix frontend run test:e2e
```

## Environment Variables

The canonical template is `.env.example` at the repo root. It includes:

- Core auth and encryption keys
- Database and Redis settings
- Optional email, captcha, analytics, and Stripe settings
- Frontend deployment metadata such as `NEXT_PUBLIC_SITE_URL`

## Project Structure

```text
repo/
├─ restailor/           # Core Python package
├─ frontend/            # Next.js app
├─ tests/               # Backend tests
├─ examples/            # Usage examples
├─ docs/                # Architecture and operational docs
├─ scripts/             # Retained helper scripts
├─ docker/              # Dockerfiles and compose files
├─ main.py              # API entrypoint
├─ worker.py            # Worker entrypoint
├─ README.md
├─ LICENSE
├─ CONTRIBUTING.md
└─ .env.example
```

## Documentation

- `docs/architecture.md`: component and deployment overview
- `docs/DEPLOYMENT.md`: production deployment guidance
- `docs/README.md`: extended developer documentation
- `render.example.yaml`: generic Render blueprint example for self-hosters

## Contributing

See `CONTRIBUTING.md` for setup expectations, coding standards, and pull request guidance.

## License

This project is released under the MIT License. See `LICENSE`.