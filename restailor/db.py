from __future__ import annotations

import os
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, declarative_base

# Naming convention helps Alembic autogenerate constraints/index diffs reliably
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# --- THIS IS THE CORRECTED SECTION ---
# This correctly creates the Base class that your other models will inherit from.
Base = declarative_base()
Base.metadata = MetaData(naming_convention=NAMING_CONVENTION)
# --- END OF CORRECTION ---


def _build_database_url() -> str:
    # --- Harmonize environment like scripts/run_migrations_local.ps1 ---
    # Map docker-compose style POSTGRES_* vars to DB_* if DB_* missing
    if not os.getenv("DB_USER") and os.getenv("POSTGRES_USER"):
        os.environ["DB_USER"] = os.getenv("POSTGRES_USER", "")
    if not os.getenv("DB_NAME") and os.getenv("POSTGRES_DB"):
        os.environ["DB_NAME"] = os.getenv("POSTGRES_DB", "")
    # Provide defaults similar to script
    if not os.getenv("DB_HOST"):
        os.environ["DB_HOST"] = "localhost"
    if not os.getenv("DB_PORT"):
        os.environ["DB_PORT"] = "5432"
    # Translate docker service name 'postgres' to localhost for direct local runs (tests)
    if os.getenv("DB_HOST") == "postgres":
        os.environ["DB_HOST"] = "localhost"
    # Provide DB_PASSWORD from POSTGRES_PASSWORD if missing
    if not os.getenv("DB_PASSWORD") and os.getenv("POSTGRES_PASSWORD"):
        os.environ["DB_PASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")
    # Provide a harmless PII key during tests if absent (avoids KeyError while not leaking real secret)
    if os.getenv("PYTEST_CURRENT_TEST") and not os.getenv("PII_ENCRYPTION_KEY"):
        os.environ["PII_ENCRYPTION_KEY"] = "test_ephemeral_pii_key"
    # 1) Hard override: DATABASE_URL (Render/AWS typical)
    env_url = os.getenv("DATABASE_URL")
    if env_url and env_url.strip():
        return env_url

    # 2) No defaults: require explicit parts when not using DATABASE_URL
    DB_USER = os.getenv("DB_USER")
    DB_NAME = os.getenv("DB_NAME")
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")

    missing = [k for k, v in {
        "DB_USER": DB_USER,
        "DB_NAME": DB_NAME,
        "DB_HOST": DB_HOST,
        "DB_PORT": DB_PORT,
    }.items() if not (v and str(v).strip())]

    db_password: str | None = None
    try:
        import keyring  # type: ignore
        db_password = keyring.get_password("restailor-app", "postgres_user_password")  # type: ignore[attr-defined]
    except Exception:
        db_password = None
    if not db_password:
        db_password = os.getenv("DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")

    if env_url is None and (missing or not db_password):
        # Removed implicit sqlite fallback: enforce explicit configuration.
        details = ", ".join(missing + (["DB_PASSWORD/POSTGRES_PASSWORD"] if not db_password else []))
        raise ValueError(
            f"DATABASE_URL not set and required parts missing: {details}. Provide DATABASE_URL or all DB_* plus password via keyring or env."
        )

    # Safe to synthesize when all parts present
    host_part = f"{DB_HOST}:{DB_PORT}"
    url = f"postgresql://{DB_USER}:{db_password}@{host_part}/{DB_NAME}"

    # Test fallback: if running under pytest and explicit override requests sqlite (no docker pg running)
    if (os.getenv("PYTEST_CURRENT_TEST") and os.getenv("TEST_USE_SQLITE") == "1"):
        return "sqlite+pysqlite:///:memory:"
    return url

DATABASE_URL = _build_database_url()

def _maybe_swap_for_test(url: str) -> str:
    # If test flags are set *now*, allow swap even if import order was earlier.
    if url.startswith("postgresql://") and (os.getenv("PYTEST_CURRENT_TEST") and os.getenv("TEST_USE_SQLITE") == "1"):
        return "sqlite+pysqlite:///:memory:"
    return url

_effective_url = _maybe_swap_for_test(DATABASE_URL)

# Standard SQLAlchemy setup (engine may be sqlite in tests)
engine = create_engine(_effective_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Auto-create tables for ephemeral in-memory sqlite during tests
if _effective_url.startswith("sqlite+") and ":memory:" in _effective_url and os.getenv("PYTEST_CURRENT_TEST"):
    try:
        from restailor import models  # noqa: F401 ensures model metadata imported
        Base.metadata.create_all(bind=engine)
    except Exception as e:  # pragma: no cover
        import logging as _logging
        _logging.getLogger(__name__).warning("auto table create failed: %r", e)


def get_pii_key() -> str:
    """Retrieves the PII encryption key from the OS keychain."""
    try:
        import keyring  # type: ignore
        pii_key = keyring.get_password("restailor-app", "pii_encryption_key")  # type: ignore[attr-defined]
    except Exception:
        pii_key = None
    if not pii_key:
        pii_key = os.getenv("PII_ENCRYPTION_KEY")
    if not pii_key:
        raise ValueError(
            "PII encryption key not found. Set keyring service='restailor-app', username='pii_encryption_key' or env PII_ENCRYPTION_KEY."
        )
    return str(pii_key)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
