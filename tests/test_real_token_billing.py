"""Tests for real token billing with estimate fallback."""
from __future__ import annotations

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session

from restailor.models import Charge, User, UserBalance, Job
from restailor.db import SessionLocal
from services.postprocess import record_charge_for_job
from services.pricing import load_price_map

pytestmark = pytest.mark.critical


@pytest.fixture()
def db_session():
    """Provide a database session for tests."""
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def user_with_balance(db_session: Session) -> User:
    """Create a test user with sufficient balance."""
    unique_id = str(uuid.uuid4())[:8]
    u = User(
        username=f"testuser_{unique_id}@example.com",
        hashed_password="fake_hash",
        role="user",
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()
    
    # Mark as test user after creation
    try:
        setattr(u, "is_test", True)
    except Exception:
        pass
    
    ub = UserBalance(user_id=u.id, balance_cents=100000, is_test=True)  # $1000
    db_session.add(ub)
    db_session.commit()
    return u


@pytest.fixture
def test_job(db_session: Session, user_with_balance: User) -> Job:
    """Create a test job."""
    j = Job(
        user_id=user_with_balance.id,
        status="queued",
        job_flow="tailor",
        input_hash=f"test_hash_{uuid.uuid4().hex[:8]}",
        access_token=f"test_token_{uuid.uuid4().hex[:16]}",
        is_test=True,
    )
    db_session.add(j)
    db_session.commit()
    return j


def test_billing_uses_real_tokens_when_available(db_session: Session, user_with_balance: User, test_job: Job):
    """Verify that billing uses real tokens when both prompt and completion are provided."""
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    
    # Estimated tokens
    est_prompt = 1000
    est_completion = 500
    
    # Real tokens (different from estimates)
    real_prompt = 1050  # 5% more
    real_completion = 480  # 4% less
    
    initial_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    
    record_charge_for_job(
        db_session,
        user_id=user_with_balance.id,
        job_id=test_job.id,
        request_type="tailor",
        provider="openai",
        model=model,
        prompt_tokens=est_prompt,
        completion_tokens=est_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=real_prompt,
        completion_tokens_real=real_completion,
        token_estimation_method="heuristic_v1",
    )
    
    db_session.commit()
    
    # Verify charge was created
    charge = db_session.query(Charge).filter(Charge.job_id == test_job.id).one()
    
    # Check that both estimated and real values are stored
    assert charge.prompt_tokens == est_prompt
    assert charge.completion_tokens == est_completion
    assert charge.prompt_tokens_real == real_prompt
    assert charge.completion_tokens_real == real_completion
    
    # Check that real prices are calculated
    assert charge.price_to_user_usd_real is not None
    assert charge.cost_usd_real is not None
    
    # Check that token estimation method is updated to provider_usage
    assert charge.token_estimation_method == "provider_usage"
    
    # Verify balance was debited using REAL price
    final_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    debit_amount = initial_balance - final_balance
    
    # Calculate expected debit from real price
    from services.pricing import to_cents
    expected_debit = to_cents(charge.price_to_user_usd_real)
    
    assert debit_amount == expected_debit
    assert abs(charge.price_to_user_usd_real - charge.price_to_user_usd) > 0  # Prices differ


def test_billing_falls_back_to_estimates_when_no_real_tokens(
    db_session: Session, user_with_balance: User, test_job: Job
):
    """Verify that billing uses estimates when real tokens are not available."""
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    
    est_prompt = 1000
    est_completion = 500
    
    initial_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    
    # Don't provide real tokens
    record_charge_for_job(
        db_session,
        user_id=user_with_balance.id,
        job_id=test_job.id,
        request_type="tailor",
        provider="openai",
        model=model,
        prompt_tokens=est_prompt,
        completion_tokens=est_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        token_estimation_method="heuristic_v1",
    )
    
    db_session.commit()
    
    charge = db_session.query(Charge).filter(Charge.job_id == test_job.id).one()
    
    # Check that only estimated values are stored
    assert charge.prompt_tokens == est_prompt
    assert charge.completion_tokens == est_completion
    assert charge.prompt_tokens_real is None
    assert charge.completion_tokens_real is None
    assert charge.price_to_user_usd_real is None
    assert charge.cost_usd_real is None
    
    # Check that token estimation method remains as provided
    assert charge.token_estimation_method == "heuristic_v1"
    
    # Verify balance was debited using ESTIMATED price
    final_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    debit_amount = initial_balance - final_balance
    
    from services.pricing import to_cents
    expected_debit = to_cents(charge.price_to_user_usd)
    
    assert debit_amount == expected_debit


def test_billing_ignores_partial_real_tokens(db_session: Session, user_with_balance: User, test_job: Job):
    """Verify that billing uses estimates when only one side has real tokens."""
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    
    est_prompt = 1000
    est_completion = 500
    real_prompt = 1050  # Only prompt has real value
    
    initial_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    
    record_charge_for_job(
        db_session,
        user_id=user_with_balance.id,
        job_id=test_job.id,
        request_type="tailor",
        provider="openai",
        model=model,
        prompt_tokens=est_prompt,
        completion_tokens=est_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=real_prompt,  # Only prompt
        completion_tokens_real=None,  # No completion
        token_estimation_method="heuristic_v1",
    )
    
    db_session.commit()
    
    charge = db_session.query(Charge).filter(Charge.job_id == test_job.id).one()
    
    # Real tokens are stored but not used for billing
    assert charge.prompt_tokens_real == real_prompt
    assert charge.completion_tokens_real is None
    assert charge.is_partial_real_tokens is True
    
    # Real prices should NOT be calculated (partial data)
    assert charge.price_to_user_usd_real is None
    assert charge.cost_usd_real is None
    
    # Verify balance was debited using ESTIMATED price (fallback)
    final_balance = db_session.get(UserBalance, user_with_balance.id).balance_cents
    debit_amount = initial_balance - final_balance
    
    from services.pricing import to_cents
    expected_debit = to_cents(charge.price_to_user_usd)
    
    assert debit_amount == expected_debit


def test_analytics_prefer_real_prices(db_session: Session, user_with_balance: User):
    """Verify that analytics functions use real prices when available."""
    from services.analytics import trimmed_average_last100_price
    
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    
    # Create multiple charges with real tokens
    for i in range(5):
        j = Job(
            user_id=user_with_balance.id,
            status="completed",
            job_flow="tailor",
            input_hash=f"test_hash_{uuid.uuid4().hex[:8]}",
            access_token=f"test_token_{uuid.uuid4().hex[:16]}",
            is_test=True,
        )
        db_session.add(j)
        db_session.flush()
        
        record_charge_for_job(
            db_session,
            user_id=user_with_balance.id,
            job_id=j.id,
            request_type="tailor",
            provider="openai",
            model=model,
            prompt_tokens=1000,
            completion_tokens=500,
            price_map=pm,
            pricing_version=int(pm.get("version", 1)),
            prompt_tokens_real=1050,  # Consistently higher
            completion_tokens_real=480,  # Consistently lower
        )
    
    # Create some charges with only estimates
    for i in range(3):
        j = Job(
            user_id=user_with_balance.id,
            status="completed",
            job_flow="tailor",
            input_hash=f"test_hash_{uuid.uuid4().hex[:8]}",
            access_token=f"test_token_{uuid.uuid4().hex[:16]}",
            is_test=True,
        )
        db_session.add(j)
        db_session.flush()
        
        record_charge_for_job(
            db_session,
            user_id=user_with_balance.id,
            job_id=j.id,
            request_type="tailor",
            provider="openai",
            model=model,
            prompt_tokens=1000,
            completion_tokens=500,
            price_map=pm,
            pricing_version=int(pm.get("version", 1)),
        )
    
    db_session.commit()
    
    # Get average - should prefer real prices (filter to this user only)
    result = trimmed_average_last100_price(
        db_session,
        global_scope=False,
        user_id=user_with_balance.id,
        trim_frac=0.0,
        include_test_rows=True,
    )
    
    assert result["n"] == 8  # All charges counted
    assert result["avg_price"] is not None
    
    # The average should be influenced by the real prices
    # (This is a basic smoke test - exact value depends on price map)
    assert result["avg_price"] > Decimal(0)
