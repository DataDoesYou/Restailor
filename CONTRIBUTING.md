# Contributing

## Development Setup

1. Fork the repository and clone your fork.
2. Copy `.env.example` to `.env` and fill in local values.
3. Install backend dependencies with `poetry install`.
4. Install frontend dependencies with `npm --prefix frontend install`.
5. Start local services with Docker Compose or your own Postgres and Redis instances.

## Recommended Workflow

1. Create a feature branch from `main`.
2. Keep changes focused and avoid unrelated formatting churn.
3. Add or update tests when behavior changes.
4. Run the relevant checks before opening a pull request.

## Checks

```bash
poetry run pytest
npm --prefix frontend run test
npm --prefix frontend run build
```

Run the E2E suite when your change affects authentication, history, analytics, or streaming flows.

## Pull Requests

- Describe the problem and the change clearly.
- Mention schema, env, or deployment impacts.
- Include screenshots for UI changes when useful.
- Do not include secrets, local databases, auth state, or generated artifacts.

## Security

If you discover a security issue, do not open a public issue with exploit details. Report it privately to the maintainers through the contact channel documented in the repository settings for your fork or deployment.