# FastAPI dev image (no source copied; bind-mount at runtime)
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps commonly needed (build tools, psycopg2, etc.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl git \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# If pyproject.toml exists, install Poetry and project deps; else use requirements.txt
COPY pyproject.toml poetry.lock* ./
RUN if [ -f "pyproject.toml" ]; then \
      curl -sSL https://install.python-poetry.org | python3 - --version 1.8.3; \
      export PATH="/root/.local/bin:$PATH"; \
  poetry config virtualenvs.create false; \
  poetry install --no-interaction --no-ansi --no-root; \
    fi

COPY requirements.txt ./
RUN if [ ! -f "pyproject.toml" ] && [ -f "requirements.txt" ]; then \
      pip install -r requirements.txt; \
    fi


EXPOSE 8000

# No CMD here; compose will provide the command (e.g., uvicorn with --reload)

# --- Production image: copy source and run uvicorn (no reload) ---
FROM base AS prod
WORKDIR /app
COPY . /app
# Default runtime command; can be overridden in compose
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
