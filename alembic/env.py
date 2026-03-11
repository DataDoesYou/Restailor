from __future__ import annotations

import os
from logging.config import fileConfig
import logging

# Import keyring at the top
import keyring
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv, find_dotenv

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Load environment variables from .env if present (do not override existing)
try:
    load_dotenv(find_dotenv(), override=False)
except Exception as ex:
    logging.getLogger("alembic.env").debug("load_dotenv failed: %s", ex)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from restailor import models  # noqa: F401
from restailor.db import Base

target_metadata = Base.metadata


def _config_or_env_url() -> str | None:
    """Return URL from environment overrides only.

    We intentionally do NOT fallback to alembic.ini here so that the builder
    (keyring/.env) can take precedence over static ini defaults.
    """
    for env_name in ("ALEMBIC_SQLALCHEMY_URL", "DATABASE_URL", "ADMIN_DATABASE_URL"):
        v = os.getenv(env_name)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def get_url() -> str:
    """Build a default database URL (keyring) if none provided via config/env.

    This ensures Alembic uses the same, up-to-date credentials as the main application,
    while allowing tests to inject a temp database URL.
    """
    override = _config_or_env_url()
    if override:
        return override
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = (
        keyring.get_password("restailor-app", "postgres_user_password")
        or os.getenv("DB_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
    )
    DB_NAME = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB") or "restailor"
    # Prefer the docker service name if present; else fall back to localhost for host usage
    DB_HOST = os.getenv("DB_HOST") or os.getenv("POSTGRES_HOST") or os.getenv("POSTGRES_SERVICE_HOST") or "localhost"
    DB_PORT = os.getenv("DB_PORT", "")

    if not DB_PASSWORD:
        raise ValueError("Database password not found in keyring! Please run the setup script.")

    host_part = f"{DB_HOST}:{DB_PORT}" if DB_PORT else DB_HOST
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{host_part}/{DB_NAME}"


def run_migrations_offline() -> None:
    url = _config_or_env_url() or get_url() or config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    # Determine URL in priority order: env overrides first, then builder (keyring/.env), finally ini default
    env_override = _config_or_env_url()
    explicit_url = config.get_main_option("sqlalchemy.url")
    try:
        built_url = get_url()
    except Exception as ex:
        logging.getLogger("alembic.env").debug("get_url failed, falling back: %s", ex)
        built_url = None
    chosen_url = env_override or built_url or explicit_url
    if not chosen_url:
        raise RuntimeError("Database URL not configured. Set DATABASE_URL or DB_* env vars, or configure keyring.")
    # Log which URL source was chosen (mask password)
    url_for_log = str(chosen_url)
    try:
        # basic masking of password in URL
        if "postgresql" in url_for_log and "@" in url_for_log and ":" in url_for_log.split("@")[0]:
            prefix, rest = url_for_log.split("@", 1)
            user_part = prefix.split("//", 1)[-1]
            if ":" in user_part:
                user, _pwd = user_part.split(":", 1)
                url_for_log = f"postgresql://{user}:***@{rest}"
    except Exception as ex:
        logging.getLogger("alembic.env").debug("mask url_for_log failed: %s", ex)
    source = "env" if env_override else ("built" if built_url else "ini")
    logging.getLogger("alembic.env").info("Using database URL (source: %s): %s", source, url_for_log)

    configuration["sqlalchemy.url"] = str(chosen_url)

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()