from __future__ import annotations

from typing import Optional
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from restailor.models import CreditLedger, UserBalance
from services.money import format_usd
import logging

logger = logging.getLogger(__name__)


def _balance_payload(cents: int) -> dict:
    """Serialize balance for API responses.

    Returns a dict with both cents and formatted USD string.
    """
    return {"balance_cents": int(cents), "balance_usd": format_usd(int(cents))}


def _lock_balance_row(session: Session, user_id: int) -> UserBalance:
    """Fetch the balance row FOR UPDATE; create if missing.

    Ensures a locked row exists so concurrent updates serialize.
    """
    bal = session.execute(
        select(UserBalance).where(UserBalance.user_id == user_id).with_for_update()
    ).scalar_one_or_none()

    if bal is None:
        from restailor.test_flags import is_automated_test_run as _is_auto
        _is_test = bool(_is_auto())
        bal = UserBalance(user_id=user_id, balance_cents=0, is_test=_is_test)
        session.add(bal)
        # Flush so the row exists within this transaction
        session.flush()
        # No separate lock needed; we're the creator within this txn

    return bal


def gift_credits(
    session: Session,
    *,
    admin_user_id: Optional[int],
    target_user_id: int,
    amount_cents: int,
    reason: Optional[str],
    idempotency_key: Optional[str],
    is_trial: bool = False,
) -> int:
    """
    Credit a user's balance by amount_cents and record a ledger entry, atomically.

    Idempotent via provider_ref: "admin:<admin_user_id or 'api'>:<idempotency_key or uuid4()>".
    
    Args:
        is_trial: If True, creates trial credits (like signup_grant), else regular grant
    
    Returns the new balance_cents.
    """
    if not isinstance(amount_cents, int) or amount_cents <= 0 or amount_cents > 1_000_000:
        raise ValueError("invalid amount_cents")

    provider_ref = f"admin:{admin_user_id if admin_user_id is not None else 'api'}:{idempotency_key or str(uuid4())}"

    # If provider_ref already exists, don't double-credit
    exists = session.execute(
        select(CreditLedger.id).where(CreditLedger.provider_ref == provider_ref)
    ).scalar_one_or_none()
    if exists:
        bal = session.get(UserBalance, target_user_id)
        try:
            logger.info(
                "admin_credits.idempotent_hit: admin_id=%s target_user_id=%s amount_cents=%s provider_ref=%s is_trial=%s",
                admin_user_id,
                target_user_id,
                amount_cents,
                provider_ref,
                is_trial,
            )
        except Exception as ex:
            logger.debug("admin_credits: idempotent log failed: %s", ex)
        return bal.balance_cents if bal else 0

    # Lock/create balance row
    bal = _lock_balance_row(session, target_user_id)

    # Insert ledger row
    from restailor.test_flags import is_automated_test_run as _is_auto
    _is_test = bool(_is_auto())
    
    # For trial credits, use note="signup_grant" to match the trial balance calculation logic
    note = f"admin_trial_gift:{reason or ''}" if is_trial else f"admin_gift:{reason or ''}"
    if is_trial:
        note = "signup_grant"  # Use same note as signup grants so it's treated as trial balance
    
    entry = CreditLedger(
        user_id=target_user_id,
        admin_id=admin_user_id,
        delta_cents=amount_cents,
        type="grant",
        note=note,
        provider_ref=provider_ref,
        is_test=_is_test,
    )
    session.add(entry)

    # Update balance
    bal.balance_cents = bal.balance_cents + amount_cents
    # mark as test only in pytest runs
    try:
        bal.is_test = _is_test
    except Exception as ex:
        logger.debug("admin_credits: set is_test failed: %s", ex)
    session.flush()
    try:
        logger.info(
            "admin_credits.gift_applied: admin_id=%s target_user_id=%s amount_cents=%s reason=%s provider_ref=%s is_trial=%s new_balance=%s",
            admin_user_id,
            target_user_id,
            amount_cents,
            (reason or ""),
            provider_ref,
            is_trial,
            bal.balance_cents,
        )
    except Exception as ex:
        logger.debug("admin_credits: gift_applied log failed: %s", ex)
    return bal.balance_cents


async def send_gift_email_notification(target_email: str, amount_cents: int, is_trial: bool) -> bool:
    """Send an email notification to user about received gift credits.
    
    Args:
        target_email: Email address of the recipient
        amount_cents: Amount of credits gifted in cents
        is_trial: True if trial credits, False if regular credits
        
    Returns True if email sent successfully, False otherwise.
    """
    try:
        from services.emailer import send_gift_notification_email
        amount_usd = format_usd(amount_cents)
        result = await send_gift_notification_email(target_email, amount_usd, is_trial)
        return result
    except Exception as ex:
        logger.warning("admin_credits.send_gift_email failed: %s", ex)
        return False
