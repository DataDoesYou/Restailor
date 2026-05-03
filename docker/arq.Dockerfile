# ARQ worker dev image (no source copied; bind-mount at runtime)
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DOPPLER_CONFIG_DIR=/tmp/.doppler

WORKDIR /app

# System deps for building wheels and postgres driver
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl git \
    gnupg gpgv libpq-dev \
 && rm -rf /var/lib/apt/lists/*

RUN curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh | sh

# Prefer Poetry if pyproject exists, else requirements.txt
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


# No default CMD; compose (dev) runs `poetry run arq worker.WorkerSettings` (hot reload disabled)

# --- Production image: copy source and run ARQ worker ---
FROM base AS prod
WORKDIR /app
COPY . /app
CMD ["sh", "-c", "doppler run -p ${DOPPLER_PROJECT:-restailor} -c ${DOPPLER_CONFIG:-prd} -- arq worker.WorkerSettings"]
