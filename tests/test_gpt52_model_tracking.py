"""Test that GPT-5.2 virtual model IDs are preserved in database for analytics."""
import uuid
import pytest
from sqlalchemy.orm import Session
from restailor.models import Charge, User, Job
from restailor.db import SessionLocal
from services.postprocess import record_charge_for_job
from services.pricing import load_price_map


@pytest.fixture()
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_user(session: Session) -> User:
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


def test_gpt52_chat_latest_stored_correctly(db_session: Session):
    """Verify that gpt-5.3-chat-latest virtual model ID is stored in charges table."""
    user = _mk_user(db_session)
    job = _mk_job(db_session, user.id)
    pm = load_price_map()
    
    # Simulate recording a charge for GPT-5.3 Chat using gpt-5 pricing (exists in config)
    record_charge_for_job(
        session=db_session,
        user_id=user.id,
        job_id=job.id,
        request_type="fit",
        provider="openai",
        model="gpt-5.3-chat-latest",  # Virtual model ID from frontend
        prompt_tokens=1000,
        completion_tokens=500,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
    )
    
    # Query the charge
    charge = db_session.query(Charge).filter(Charge.job_id == job.id).first()
    
    assert charge is not None
    # THIS IS THE KEY TEST - we expect the virtual ID to be preserved
    assert charge.model == "gpt-5.3-chat-latest", f"Expected 'gpt-5.3-chat-latest' but got '{charge.model}' - virtual ID not preserved!"
    assert charge.provider == "openai"


def test_gpt52_stored_correctly(db_session: Session):
    """Verify that gpt-5.4 virtual model ID is stored in charges table."""
    user = _mk_user(db_session)
    job = _mk_job(db_session, user.id)
    pm = load_price_map()
    
    # Simulate recording a charge for GPT-5.2
    record_charge_for_job(
        session=db_session,
        user_id=user.id,
        job_id=job.id,
        request_type="fit",
        provider="openai",
        model="gpt-5.4",  # Virtual model ID from frontend
        prompt_tokens=1000,
        completion_tokens=500,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
    )
    
    # Query the charge
    charge = db_session.query(Charge).filter(Charge.job_id == job.id).first()
    
    assert charge is not None
    assert charge.model == "gpt-5.4", f"Expected 'gpt-5.4' but got '{charge.model}'"
    assert charge.provider == "openai"


def test_gpt52_models_distinct_in_analytics(db_session: Session):
    """Verify that gpt-5.3-chat-latest and gpt-5.4 appear as separate entries in analytics."""
    user = _mk_user(db_session)
    job_instant = _mk_job(db_session, user.id)
    job_thinking = _mk_job(db_session, user.id)
    pm = load_price_map()
    
    # Add charges for both models
    record_charge_for_job(
        session=db_session,
        user_id=user.id,
        job_id=job_instant.id,
        request_type="fit",
        provider="openai",
        model="gpt-5.3-chat-latest",
        prompt_tokens=1000,
        completion_tokens=500,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
    )
    
    record_charge_for_job(
        session=db_session,
        user_id=user.id,
        job_id=job_thinking.id,
        request_type="fit",
        provider="openai",
        model="gpt-5.4",
        prompt_tokens=2000,
        completion_tokens=1000,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
    )
    
    # Query distinct models
    distinct_models = db_session.query(Charge.model).filter(
        Charge.user_id == user.id,
        Charge.model.like("gpt-5.4%")
    ).distinct().all()
    
    model_names = [m[0] for m in distinct_models]
    
    assert "gpt-5.3-chat-latest" in model_names, "gpt-5.3-chat-latest should appear in analytics"
    assert "gpt-5.4" in model_names, "gpt-5.4 should appear in analytics"
    assert len(model_names) == 2, f"Expected 2 distinct models, got {len(model_names)}: {model_names}"


def test_legacy_gpt51_still_supported(db_session: Session):
    """Verify that legacy gpt-5.1 (without suffix) is still supported for old records."""
    user = _mk_user(db_session)
    job = _mk_job(db_session, user.id)
    pm = load_price_map()
    
    # Simulate an old charge with the legacy model ID
    record_charge_for_job(
        session=db_session,
        user_id=user.id,
        job_id=job.id,
        request_type="fit",
        provider="openai",
        model="gpt-5.1",  # Legacy format
        prompt_tokens=1000,
        completion_tokens=500,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
    )
    
    charge = db_session.query(Charge).filter(Charge.job_id == job.id).first()
    
    assert charge is not None
    assert charge.model == "gpt-5.1"
