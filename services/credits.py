from __future__ import annotations

from typing import Any
import hashlib
import ipaddress
import logging

from fastapi import Request
from slowapi.util import get_remote_address
from sqlalchemy import select
from restailor.constants import days_to_seconds
from sqlalchemy.orm import Session

from restailor.models import CreditLedger, UserBalance, User

logger = logging.getLogger(__name__)


# --- Stripe considerations (future-proofing) ---
# Single source of truth:
#   Keep ALL money movements in CreditLedger and UserBalance.
#
# Grant vs purchase:
#   - Signup grant → type='grant', positive delta_cents.
#   - Stripe purchase → type='purchase', positive delta_cents, provider_ref=<checkout_session_id or payment_intent_id>.
#   - Refund/chargeback → type='refund', negative delta_cents, referencing the same provider_ref.
#
# Idempotency:
#   Stripe webhooks can fire more than once; upsert/check by provider_ref so you don't double-credit.
#
# Order of operations:
#   - On checkout.session.completed (or payment_intent.succeeded): credit the balance (insert ledger row, bump UserBalance).
#   - On charge.refunded or refund.succeeded: insert a refund ledger row with negative delta and decrement UserBalance.
#
# Reporting:
#   With both CreditLedger and charges, you can compute revenue/MRR-like metrics and reconcile spend vs revenue.
#
# Fraud guard:
#   Keep the signup grant small (e.g., $1), require email verification before spend if abuse becomes an issue.
#   Jobs should already enforce price <= balance; keep that invariant.


def _normalize_email_for_abuse_checks(email: str) -> str:
    e = (email or "").strip().lower()
    try:
        if not e or "@" not in e:
            return e
        local, domain = e.split("@", 1)
        try:
            domain = domain.encode("idna").decode("ascii")
        except Exception as ex:
            logger.debug("credits._normalize_email_for_abuse_checks: IDNA encode failed: %s", ex)
        if domain in ("gmail.com", "googlemail.com"):
            if "+" in local:
                local = local.split("+", 1)[0]
            local = local.replace(".", "")
            domain = "gmail.com"
        return f"{local}@{domain}"
    except Exception:
        return e


def _derive_fingerprint(request: Request, user: User | Any) -> str:
    fp = getattr(user, "browser_fingerprint", None)
    if fp:
        return str(fp)
    ua = request.headers.get("user-agent", "").strip()
    al = request.headers.get("accept-language", "").strip()
    ip = (get_remote_address(request) or "").strip()
    ip_pref = ip
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.version == 4:
            parts = ip.split(".")
            if len(parts) == 4:
                ip_pref = ".".join(parts[:3] + ["0"])  # /24
        else:
            parts = ip.split(":")
            if len(parts) >= 4:
                ip_pref = ":".join(parts[:4])
    except Exception as ex:
        logger.debug("credits._derive_fingerprint: IP parse failed: %s", ex)
    base = f"{ua}|{al}|{ip_pref}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


def already_granted_signup(session: Session, user_id: int) -> bool:
    """Return True if a signup grant ledger exists for this user."""
    try:
        row = session.execute(
            select(CreditLedger.id).where(
                (CreditLedger.user_id == int(user_id)) & (CreditLedger.note == "signup_grant")
            )
        ).scalar_one_or_none()
        return bool(row)
    except Exception as ex:
        logger.debug("credits.already_granted_signup failed: %s", ex)
        return False


async def set_gate_and_check(redis: Any, key: str, days: int) -> bool:
    """
    If 'days' > 0:
      - if key exists: return False (blocked)
      - else: SET key with TTL and return True (allowed)
    If 'days' == 0 or redis is None: return True
    """
    if redis is None:
        return True
    try:
        days = int(days or 0)
    except Exception:
        days = 0
    if days <= 0:
        return True
    ttl = days_to_seconds(days)
    try:
        # Prefer atomic SET NX with expiration if supported
        if hasattr(redis, "set"):
            ok = await redis.set(key, "1", ex=ttl, nx=True)  # type: ignore[arg-type]
            # Some clients return True/OK or None
            return bool(ok)
    except TypeError:
        # Fallback to GET+SETEX if signature mismatch
        pass
    except Exception:
        # On any error, allow to avoid hard-failing user flows
        return True
    try:
        if await redis.get(key):
            return False
        if hasattr(redis, "setex"):
            await redis.setex(key, ttl, "1")  # type: ignore[arg-type]
        else:
            await redis.set(key, "1", ex=ttl)  # type: ignore[arg-type]
        return True
    except Exception:
        return True


async def maybe_grant_signup_credit(
    session: Session,
    *,
    user: User | Any,
    cfg: dict,
    request: Request,
) -> bool:
    """
    Applies the signup grant if eligible.
    Returns True if granted, False otherwise.
    Uses:
      - CreditLedger (type='grant', delta_cents>0, note='signup_grant')
      - UserBalance increment
      - Redis-based gates if REDIS_URL configured; fall back to email-only check otherwise.
    """
    try:
        if not bool(cfg.get("enable_signup_grant", False)):  # Default disabled
            return False
        amount = int(cfg.get("signup_grant_cents", 100) or 0)
        if amount <= 0:
            return False
    except Exception as ex:
        logger.debug("credits.maybe_grant_signup_credit: config parse failed: %s", ex)
        return False

    # Idempotency: per-user ledger check
    try:
        if already_granted_signup(session, int(getattr(user, "id", 0))):
            return False
    except Exception as ex:
        logger.debug("credits.maybe_grant_signup_credit: already_granted_signup check failed: %s", ex)

    # Gates (best-effort)
    r = getattr(request.app.state, "redis", None)
    if r is not None:
        try:
            ip = (get_remote_address(request) or "").strip() or "unknown"
            email = _normalize_email_for_abuse_checks(str(getattr(user, "username", "")))
            fpr = _derive_fingerprint(request, user)
            ip_days = int(cfg.get("grant_window_ip_days", 1) or 1)
            em_days = int(cfg.get("grant_window_email_days", 7) or 7)
            fp_days = int(cfg.get("grant_window_fingerprint_days", 30) or 30)
            # Use consistent namespaces with main.py: signupgrant:*
            ok_ip = await set_gate_and_check(r, f"signupgrant:ip:{ip}", ip_days)
            ok_em = await set_gate_and_check(r, f"signupgrant:email:{email}", em_days)
            ok_fp = await set_gate_and_check(r, f"signupgrant:fp:{fpr}", fp_days)
            if not (ok_ip and ok_em and ok_fp):
                return False
        except Exception as ex:
            # If gates fail, allow grant (soft)
            logger.debug("credits.maybe_grant_signup_credit: gate checks failed: %s", ex)

    # Apply ledger + balance (within one DB transaction)
    try:
        # Lock/create balance row
        bal = session.execute(
            select(UserBalance).where(UserBalance.user_id == int(getattr(user, "id", 0))).with_for_update()
        ).scalar_one_or_none()
        if bal is None:
            from restailor.test_flags import is_automated_test_run as _is_auto
            _is_test = bool(_is_auto())
            bal = UserBalance(user_id=int(getattr(user, "id", 0)), balance_cents=0, is_test=_is_test)
            session.add(bal)
            session.flush()

        provider_ref = f"signup_grant:{int(getattr(user, 'id', 0))}"
        dup = session.execute(
            select(CreditLedger.id).where(CreditLedger.provider_ref == provider_ref)
        ).scalar_one_or_none()
        if dup:
            return False

        from restailor.test_flags import is_automated_test_run as _is_auto
        _is_test = bool(_is_auto())
        entry = CreditLedger(
            user_id=int(getattr(user, "id", 0)),
            admin_id=None,
            delta_cents=int(amount),
            type="grant",
            note="signup_grant",
            provider_ref=provider_ref,
            is_test=_is_test,
        )
        session.add(entry)
        bal.balance_cents = int(bal.balance_cents) + int(amount)
        try:
            bal.is_test = _is_test
        except Exception as ex:
            logger.debug("credits.maybe_grant_signup_credit: set is_test failed: %s", ex)
        session.commit()
        return True
    except Exception:
        try:
            session.rollback()
        except Exception as rb_ex:
            logger.debug("maybe_grant_signup_credit: rollback failed: %s", rb_ex)
        logger.debug("maybe_grant_signup_credit: rollback due to exception", exc_info=True)
        return False
