import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from restailor.models import User, Job, Charge, UserBalance
from restailor.db import SessionLocal
import pytest
from services.postprocess import record_charge_for_job
from services.pricing import load_price_map, quote_cost_usd, apply_multiplier, to_cents as pricing_to_cents

pytestmark = pytest.mark.critical


@pytest.fixture()
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_user(session: Session) -> User:
    # User model fields: username, hashed_password, role, etc.
    u = User(
        username=f"u_{uuid.uuid4()}@example.com",
        hashed_password="test_pw_hash",
        role="user",
        is_active=True,
        is_test=True,
    )
    session.add(u)
    session.commit()
    return u


def _mk_job(session: Session, user_id: int | None = None) -> Job:
    j = Job(
        status="queued",
        input_hash="ih",
        access_token=str(uuid.uuid4()),
        user_id=user_id,
        is_test=True,
    )
    session.add(j)
    session.commit()
    return j


def test_charge_created_and_balance_debited(db_session: Session):
    u = _mk_user(db_session)
    j = _mk_job(db_session, u.id)
    pm = load_price_map()
    # Pick an arbitrary existing model from price map
    model = next(iter((pm.get("models") or {}).keys()))
    prompt_tokens = 800
    completion_tokens = 200
    est_cost = quote_cost_usd(pm, model, prompt_tokens, completion_tokens)
    mult = Decimal(pm.get("multiplier", 1))
    est_price = apply_multiplier(est_cost, mult)

    record_charge_for_job(
        db_session,
        user_id=u.id,
        job_id=j.id,
        request_type="tailor",
        provider="testprov",
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        token_estimation_method="heuristic_v1",
    )
    db_session.commit()

    ch = db_session.execute(select(Charge).where(Charge.job_id == j.id)).scalar_one()
    assert ch.prompt_tokens == prompt_tokens
    assert ch.completion_tokens == completion_tokens
    assert ch.cost_usd == est_cost
    assert ch.price_to_user_usd == est_price

    ub = db_session.get(UserBalance, u.id)
    assert ub is not None
    # Balance should be negative by est_price in cents
    charged_cents = pricing_to_cents(est_price)
    assert ub.balance_cents == -charged_cents


def test_no_charge_when_missing_user_id(db_session: Session):
    j = _mk_job(db_session, None)
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    record_charge_for_job(
        db_session,
        user_id=None,
        job_id=j.id,
        request_type="tailor",
        provider="testprov",
        model=model,
        prompt_tokens=100,
        completion_tokens=50,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        token_estimation_method="heuristic_v1",
    )
    db_session.commit()
    count = db_session.execute(select(Charge).where(Charge.job_id == j.id)).scalars().all()
    assert count == []


def test_idempotent_charge(db_session: Session):
    u = _mk_user(db_session)
    j = _mk_job(db_session, u.id)
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))
    for _ in range(3):
        record_charge_for_job(
            db_session,
            user_id=u.id,
            job_id=j.id,
            request_type="tailor",
            provider="testprov",
            model=model,
            prompt_tokens=10,
            completion_tokens=5,
            price_map=pm,
            pricing_version=int(pm.get("version", 1)),
            token_estimation_method="heuristic_v1",
        )
        db_session.commit()
    rows = db_session.execute(select(Charge).where(Charge.job_id == j.id)).scalars().all()
    assert len(rows) == 1, "Expected only one charge due to idempotency"


def test_partial_real_tokens_does_not_bill_real(db_session: Session):
    u = _mk_user(db_session)
    j = _mk_job(db_session, u.id)
    pm = load_price_map()
    model = next(iter((pm.get("models") or {}).keys()))

    record_charge_for_job(
        db_session,
        user_id=u.id,
        job_id=j.id,
        request_type="tailor",
        provider="testprov",
        model=model,
        prompt_tokens=1000,
        completion_tokens=500,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=1200,
        completion_tokens_real=None,  # partial
        token_estimation_method="heuristic_v1",
    )
    db_session.commit()
    ch = db_session.execute(select(Charge).where(Charge.job_id == j.id)).scalar_one()
    assert ch.is_partial_real_tokens is True
    assert ch.cost_usd_real is None and ch.price_to_user_usd_real is None
