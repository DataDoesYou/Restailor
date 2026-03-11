import os
import uuid
from decimal import Decimal

from restailor.db import SessionLocal
from restailor.models import Charge, User, UserBalance, Job
from services.postprocess import record_charge_for_job

import pytest
pytestmark = pytest.mark.critical


def _ensure_test_user(session):
    u = User(username=f"billing_tester_{uuid.uuid4().hex[:8]}", hashed_password="x", is_test=True)
    session.add(u)
    session.flush()
    # Ensure a balance row exists with plenty of credits (0 OK since we allow negative)
    ub = UserBalance(user_id=u.id, balance_cents=100000, is_test=True)
    session.add(ub)
    session.flush()
    return u


def _new_job(session, user_id):
    j = Job(status="completed", input_hash="h", access_token="tok", user_id=user_id, is_test=True)
    session.add(j)
    session.flush()
    return j

PRICE_MAP = {
    "currency": "USD",
    # basic linear pricing: assume quote_cost_usd(price_map, model, in, out) uses these keys
    # Provide plausible structure: input_price_per_1k, output_price_per_1k
    "models": {
        "test-model": {
            "input": Decimal("0.001"),  # per token? underlying util will interpret
            "output": Decimal("0.002"),
        }
    },
    "multiplier": Decimal("5"),
}


def test_full_real_tokens_bills_from_real(monkeypatch):
    with SessionLocal() as s:
        user = _ensure_test_user(s)
        job = _new_job(s, user.id)
        # Force quote_cost_usd to a deterministic calculation independent of real impl
        from services.postprocess import quote_cost_usd as real_quote
        def fake_quote(price_map, model, prompt, completion):
            # simple: cost = prompt*0.001 + completion*0.002
            return (Decimal(prompt) * Decimal("0.001") + Decimal(completion) * Decimal("0.002")).quantize(Decimal("0.000001"))
        monkeypatch.setattr("services.postprocess.quote_cost_usd", fake_quote)
        # Use real tokens that change cost relative to estimate (est 100/50 vs real 130/40)
        record_charge_for_job(
            s,
            user_id=user.id,
            job_id=job.id,
            request_type="tailor",
            provider="test",
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            price_map=PRICE_MAP,
            pricing_version=1,
            prompt_tokens_real=130,
            completion_tokens_real=40,
            token_estimation_method="heuristic_v1",
        )
        s.commit()
        ch = s.query(Charge).filter_by(user_id=user.id, job_id=job.id).one()
        # Real billing path: *_real costs populated and debit uses those
        assert ch.prompt_tokens_real == 130
        assert ch.completion_tokens_real == 40
        assert ch.cost_usd_real is not None and ch.price_to_user_usd_real is not None
        assert ch.token_estimation_method == "provider_usage"
        # Verify exact expected values
        expected_est = fake_quote(PRICE_MAP, "test-model", 100, 50)
        expected_real = fake_quote(PRICE_MAP, "test-model", 130, 40)
        assert ch.cost_usd == expected_est
        assert ch.cost_usd_real == expected_real
        assert ch.price_to_user_usd == expected_est * PRICE_MAP["multiplier"]
        assert ch.price_to_user_usd_real == expected_real * PRICE_MAP["multiplier"]


def test_partial_real_tokens_uses_estimate(monkeypatch):
    with SessionLocal() as s:
        user = _ensure_test_user(s)
        job = _new_job(s, user.id)
        def fake_quote(price_map, model, prompt, completion):
            return (Decimal(prompt) * Decimal("0.001") + Decimal(completion) * Decimal("0.002")).quantize(Decimal("0.000001"))
        monkeypatch.setattr("services.postprocess.quote_cost_usd", fake_quote)
        record_charge_for_job(
            s,
            user_id=user.id,
            job_id=job.id,
            request_type="tailor",
            provider="test",
            model="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            price_map=PRICE_MAP,
            pricing_version=1,
            prompt_tokens_real=100,
            completion_tokens_real=None,
            token_estimation_method="heuristic_v1",
        )
        s.commit()
        ch = s.query(Charge).filter_by(user_id=user.id, job_id=job.id).one()
        assert ch.cost_usd_real is None and ch.price_to_user_usd_real is None
        assert ch.token_estimation_method == "heuristic_v1"  # unchanged
        assert ch.is_partial_real_tokens is True


def test_no_real_tokens(monkeypatch):
    with SessionLocal() as s:
        user = _ensure_test_user(s)
        job = _new_job(s, user.id)
        def fake_quote(price_map, model, prompt, completion):
            return (Decimal(prompt) * Decimal("0.001") + Decimal(completion) * Decimal("0.002")).quantize(Decimal("0.000001"))
        monkeypatch.setattr("services.postprocess.quote_cost_usd", fake_quote)
        record_charge_for_job(
            s,
            user_id=user.id,
            job_id=job.id,
            request_type="tailor",
            provider="test",
            model="test-model",
            prompt_tokens=10,
            completion_tokens=5,
            price_map=PRICE_MAP,
            pricing_version=1,
            prompt_tokens_real=None,
            completion_tokens_real=None,
            token_estimation_method="heuristic_v1",
        )
        s.commit()
        ch = s.query(Charge).filter_by(user_id=user.id, job_id=job.id).one()
        assert ch.cost_usd_real is None and ch.price_to_user_usd_real is None
        assert ch.is_partial_real_tokens is False
        assert ch.token_estimation_method == "heuristic_v1"
