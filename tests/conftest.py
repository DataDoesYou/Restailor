import pytest
import os
import pathlib

# --- Doppler / Postgres test bootstrap ---
# Enforce running tests through scripts/run_tests_local.ps1 (sets RUN_TESTS_VIA_SCRIPT=1)
if not os.getenv("RUN_TESTS_VIA_SCRIPT"):
    pytest.skip("Run tests via scripts/run_tests_local.ps1 (Doppler env + migrations).", allow_module_level=True)
# We expect tests to be invoked via:
#   doppler run -- poetry run pytest -vv
# so all required secrets & DB vars are present in the environment already.

REQUIRED_DB_VARS = ["DATABASE_URL"]  # prefer full URL; fallback parts optional
FALLBACK_PARTS = ["DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT"]

def _synthesize_url_from_parts() -> None:
    if os.getenv("DATABASE_URL"):
        return
    parts_missing = [k for k in ("DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(k)]
    if parts_missing:
        return  # leave unset; skip will trigger below
    host = os.getenv("DB_HOST", "localhost")
    if host == "postgres":
        host = "localhost"
    port = os.getenv("DB_PORT", "5432")
    os.environ["DATABASE_URL"] = (
        f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{host}:{port}/{os.environ['DB_NAME']}"
    )

_synthesize_url_from_parts()

# Provide lightweight test defaults for app-required secrets if Doppler didn't set them (should normally be set)
os.environ.setdefault("AUTH_SECRET_KEY", "test_auth_secret")
os.environ.setdefault("PII_ENCRYPTION_KEY", "test_local_pii_key")
os.environ.setdefault("VERIFY_SECRET_KEY", "test_verify_secret")
os.environ.setdefault("RESET_SECRET_KEY", "test_reset_secret")

if not os.getenv("DATABASE_URL"):
    reason = (
        "DATABASE_URL not present in environment. Run tests with Doppler: "
        "doppler run -- poetry run pytest -vv"
    )
    pytest.skip(reason, allow_module_level=True)

# Run migrations once (idempotent) against the Postgres DATABASE_URL
try:
    from alembic.config import Config as _AlConfig  # noqa: E402
    from alembic import command as _alcmd  # noqa: E402
    cfg = _AlConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    _alcmd.upgrade(cfg, "head")
except Exception as _e:  # pragma: no cover
    raise RuntimeError(f"Alembic migration failed in test bootstrap: {_e}")


def _disable_login_captcha():
    try:
        import main  # the FastAPI app module
        auth = main.CONFIG.setdefault("auth", {})
        login = auth.setdefault("login", {})
        captcha = login.setdefault("captcha", {})
        captcha["required"] = False
    except Exception:
        # Best effort; tests that rely on login will set X-Client-Id too
        pass


@pytest.fixture(autouse=True, scope="session")
def _patch_login_captcha_off():
    _disable_login_captcha()
    yield
    # no teardown needed


@pytest.fixture(autouse=True, scope="session")
def _disable_outbound_email_for_tests():
    # Ensure no real emails are sent during pytest runs
    os.environ.setdefault("EMAIL_DISABLE_OUTBOUND", "1")
    os.environ.setdefault("DISABLE_OUTBOUND_EMAIL", "1")
    # Relax strict secret checks during tests so the app can start without keyring/env secrets
    os.environ.setdefault("STRICT_SECRETS", "0")
    # Enable test-only endpoints and mark data as test in server code
    os.environ.setdefault("E2E_TEST_MODE", "1")
    # Disable CAPTCHA requirements during tests (login/signup)
    os.environ.setdefault("LOGIN_CAPTCHA_REQUIRED", "0")
    os.environ.setdefault("SIGNUP_CAPTCHA_REQUIRED", "0")
    # Prefer in-memory fallbacks over Redis during tests
    os.environ.setdefault("DISABLE_REDIS", "1")
    # Avoid requiring Turnstile secrets locally
    os.environ.setdefault("TURNSTILE_SECRET_KEY", "")
    yield
    # leave env as-is


@pytest.fixture(autouse=False, scope="session")  # DISABLED: Keep test data for inspection
def _cleanup_test_data_at_session_end():
    """After the entire test session, purge rows flagged as is_test to keep the DB clean.

    We only delete rows that have is_test = True, which our tests set on created Users,
    Charges, UserBalance, etc. This keeps production/demo data intact.
    
    NOTE: Currently disabled (autouse=False) to preserve test data for manual inspection.
    """
    yield
    try:
        from restailor.db import SessionLocal
        from restailor.models import (
            User,
            Job,
            JobOutput,
            Charge,
            CreditLedger,
            UserBalance,
            EmailLog,
            AnalyticsJobSnapshotState,
        )
        with SessionLocal() as s:
            # Delete dependent rows first to satisfy FKs and reduce cascades
            try:
                s.query(JobOutput).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(Charge).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(CreditLedger).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(EmailLog).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(AnalyticsJobSnapshotState).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(Job).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(UserBalance).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.query(User).filter_by(is_test=True).delete(synchronize_session=False)
            except Exception:
                pass
            try:
                s.commit()
            except Exception:
                s.rollback()
    except Exception:
        # Best-effort cleanup; ignore if DB unavailable or schema differs
        pass


# Ensure JobOutput rows created by prior tests do not leak into tests that assert none exist.
# Limiting to is_test=True preserves non-test data.
@pytest.fixture(autouse=True)
def _clear_test_job_outputs_before_each_test():
    try:
        from restailor.db import SessionLocal
        from restailor.models import JobOutput, AnalyticsJobSnapshotState
        with SessionLocal() as s:
            try:
                s.query(JobOutput).filter_by(is_test=True).delete(synchronize_session=False)
                s.query(AnalyticsJobSnapshotState).filter_by(is_test=True).delete(synchronize_session=False)
                s.commit()
            except Exception:
                s.rollback()
    except Exception:
        # best-effort
        pass


# Quarantine support: if a test file is under tests_quarantine/, skip it automatically
@pytest.fixture(autouse=True)
def _skip_quarantined_tests(request: pytest.FixtureRequest):
    try:
        fpath = pathlib.Path(str(getattr(request.node, "fspath", "")))
        # 1) Skip anything under tests_quarantine/
        if any(part.lower() == "tests_quarantine" for part in fpath.parts):
            pytest.skip("Quarantined test (folder)")
        # 2) Skip files listed in quarantine.txt at repo root
        root = pathlib.Path(__file__).resolve().parent.parent
        qfile = root / "quarantine.txt"
        if qfile.exists():
            rel = fpath.resolve().as_posix().lower()
            # Normalize to repo-relative
            try:
                rel_repo = fpath.resolve().relative_to(root).as_posix().lower()
            except Exception:
                rel_repo = rel
            pats: list[str] = []
            for line in qfile.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Remove trailing comments
                if "#" in line:
                    line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                pats.append(line.strip().lower())
            for p in pats:
                if p.endswith("/**"):
                    # directory glob: skip if path starts with that prefix
                    pref = p[:-3].rstrip("/")
                    if rel_repo.startswith(pref):
                        pytest.skip("Quarantined test (list)")
                else:
                    if rel_repo == p or rel_repo.endswith("/" + p.strip("/")):
                        pytest.skip("Quarantined test (list)")
    except Exception:
        # best-effort
        pass
