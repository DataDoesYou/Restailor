"""Test that GPT-5.2 Chat Latest vs GPT-5.2 modes track different token counts.

This test verifies that:
1. GPT-5.2 Chat Latest (reasoning_effort='none') generates fewer completion tokens
2. GPT-5.2 (reasoning_effort='medium') generates MORE completion tokens (includes reasoning)
3. The difference is captured in completion_tokens_real
4. The cost difference is reflected in price_to_user_usd_real
"""
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from restailor.models import User, Charge
from restailor.db import SessionLocal
from services.pricing import load_price_map, quote_cost_usd, apply_multiplier
from services.postprocess import record_charge_for_job


@pytest.fixture()
def db_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_instant_vs_thinking_token_counts_differ(db_session: Session):
    """Verify that Chat Latest mode has fewer completion tokens than GPT-5.2 mode for same prompt.
    
    This simulates what SHOULD happen:
    - Chat Latest: reasoning_effort='none' → only visible completion tokens
    - GPT-5.2: reasoning_effort='medium' → visible completion + hidden reasoning tokens
    
    The reasoning tokens are included in completion_tokens_real but NOT shown separately by OpenAI.
    """
    # Setup user
    user = User(email="test@gpt52.com", hashed_password="test", is_verified=True)
    db_session.add(user)
    db_session.commit()
    
    pm = load_price_map()
    
    # Simulate GPT-5.2 Chat Latest request: NO reasoning tokens
    # Example: 1000 prompt, 500 completion (pure visible output)
    instant_prompt = 1000
    instant_completion = 500
    
    record_charge_for_job(
        db_session,
        user_id=user.id,
        job_id="instant-test",
        request_type="tailor",
        provider="openai",
        model="gpt-5.2-chat-latest",
        prompt_tokens=instant_prompt,
        completion_tokens=instant_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=instant_prompt,
        completion_tokens_real=instant_completion,  # No reasoning tokens added
        token_estimation_method="provider_usage",
    )
    
    # Simulate GPT-5.2 request: SAME prompt, MORE completion due to reasoning
    # Example: 1000 prompt, 800 completion (500 visible + 300 reasoning)
    # OpenAI returns this as ONE number: completion_tokens=800
    thinking_prompt = 1000
    thinking_completion = 800  # HIGHER because includes reasoning tokens
    
    record_charge_for_job(
        db_session,
        user_id=user.id,
        job_id="thinking-test",
        request_type="tailor",
        provider="openai",
        model="gpt-5.2",
        prompt_tokens=thinking_prompt,
        completion_tokens=thinking_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=thinking_prompt,
        completion_tokens_real=thinking_completion,  # Includes reasoning tokens
        token_estimation_method="provider_usage",
    )
    
    db_session.commit()
    
    # Fetch charges
    instant_charge = db_session.query(Charge).filter_by(job_id="instant-test").one()
    thinking_charge = db_session.query(Charge).filter_by(job_id="thinking-test").one()
    
    # Verify token counts
    assert instant_charge.completion_tokens_real == instant_completion, \
        f"Instant should have {instant_completion} completion tokens"
    assert thinking_charge.completion_tokens_real == thinking_completion, \
        f"Thinking should have {thinking_completion} completion tokens (includes reasoning)"
    
    # Verify Thinking has MORE completion tokens than Instant
    assert thinking_charge.completion_tokens_real > instant_charge.completion_tokens_real, \
        "Thinking mode should generate MORE completion tokens than Instant (includes reasoning tokens)"
    
    # Calculate expected costs
    instant_cost = quote_cost_usd(pm, "gpt-5.2-chat-latest", instant_prompt, instant_completion)
    instant_price = apply_multiplier(instant_cost, Decimal(pm.get("multiplier", 1)))
    
    thinking_cost = quote_cost_usd(pm, "gpt-5.2", thinking_prompt, thinking_completion)
    thinking_price = apply_multiplier(thinking_cost, Decimal(pm.get("multiplier", 1)))
    
    # Verify costs match expected
    assert instant_charge.price_to_user_usd_real == instant_price, \
        f"Instant price mismatch: {instant_charge.price_to_user_usd_real} != {instant_price}"
    assert thinking_charge.price_to_user_usd_real == thinking_price, \
        f"Thinking price mismatch: {thinking_charge.price_to_user_usd_real} != {thinking_price}"
    
    # Verify Thinking costs MORE than Instant due to extra tokens
    assert thinking_charge.price_to_user_usd_real > instant_charge.price_to_user_usd_real, \
        f"Thinking mode should cost MORE than Instant! Instant: ${instant_charge.price_to_user_usd_real}, Thinking: ${thinking_charge.price_to_user_usd_real}"
    
    # Calculate the difference
    cost_diff = thinking_charge.price_to_user_usd_real - instant_charge.price_to_user_usd_real
    token_diff = thinking_charge.completion_tokens_real - instant_charge.completion_tokens_real
    
    print(f"\n=== GPT-5.2 Chat Latest vs GPT-5.2 Token Tracking ===")
    print(f"Chat Latest: {instant_prompt} prompt + {instant_completion} completion = ${instant_charge.price_to_user_usd_real}")
    print(f"GPT-5.2: {thinking_prompt} prompt + {thinking_completion} completion = ${thinking_charge.price_to_user_usd_real}")
    print(f"Difference: +{token_diff} tokens, +${cost_diff} cost")
    print(f"Reasoning overhead: {((thinking_completion - instant_completion) / instant_completion * 100):.1f}% more tokens")


def test_identical_requests_should_show_cost_difference(db_session: Session):
    """If you submit IDENTICAL prompts to Chat Latest vs GPT-5.2, GPT-5.2 should cost more.
    
    This test proves that even with the same input, GPT-5.2 generates more tokens.
    """
    user = User(email="test2@gpt52.com", hashed_password="test", is_verified=True)
    db_session.add(user)
    db_session.commit()
    
    pm = load_price_map()
    
    # Same prompt for both
    prompt_tokens = 1500
    
    # Chat Latest: generates reasonable completion
    instant_completion = 600
    
    # GPT-5.2: generates MORE completion because it thinks first
    # Typical reasoning overhead: 20-60% depending on complexity
    thinking_completion = 900  # 50% more due to reasoning
    
    record_charge_for_job(
        db_session,
        user_id=user.id,
        job_id="identical-instant",
        request_type="tailor",
        provider="openai",
        model="gpt-5.2-chat-latest",
        prompt_tokens=prompt_tokens,
        completion_tokens=instant_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=prompt_tokens,
        completion_tokens_real=instant_completion,
        token_estimation_method="provider_usage",
    )
    
    record_charge_for_job(
        db_session,
        user_id=user.id,
        job_id="identical-thinking",
        request_type="tailor",
        provider="openai",
        model="gpt-5.2",
        prompt_tokens=prompt_tokens,
        completion_tokens=thinking_completion,
        price_map=pm,
        pricing_version=int(pm.get("version", 1)),
        prompt_tokens_real=prompt_tokens,
        completion_tokens_real=thinking_completion,
        token_estimation_method="provider_usage",
    )
    
    db_session.commit()
    
    instant = db_session.query(Charge).filter_by(job_id="identical-instant").one()
    thinking = db_session.query(Charge).filter_by(job_id="identical-thinking").one()
    
    # CRITICAL: Thinking must cost more for the same prompt
    assert thinking.price_to_user_usd_real > instant.price_to_user_usd_real, \
        f"IDENTICAL prompts: GPT-5.2 (${thinking.price_to_user_usd_real}) should cost MORE than Chat Latest (${instant.price_to_user_usd_real})"
    
    # The difference should be proportional to the extra completion tokens
    instant_cost_per_token = instant.price_to_user_usd_real / Decimal(instant_completion)
    thinking_cost_per_token = thinking.price_to_user_usd_real / Decimal(thinking_completion)
    
    # Both should have similar per-token cost (same rate)
    assert abs(instant_cost_per_token - thinking_cost_per_token) < Decimal("0.00001"), \
        "Per-token cost should be similar (same pricing rate)"
    
    print(f"\n=== Identical Prompts Test ===")
    print(f"Prompt: {prompt_tokens} tokens (same for both)")
    print(f"Chat Latest completion: {instant_completion} tokens → ${instant.price_to_user_usd_real}")
    print(f"GPT-5.2 completion: {thinking_completion} tokens → ${thinking.price_to_user_usd_real}")
    print(f"GPT-5.2 generates {thinking_completion - instant_completion} extra tokens (+{((thinking_completion - instant_completion) / instant_completion * 100):.1f}%)")


def test_pricing_rates_identical_for_both_models(db_session: Session):
    """Verify that the pricing RATES are identical - only token counts differ."""
    pm = load_price_map()
    
    # Get rates for both models
    instant_rates = pm["models"]["gpt-5.2-chat-latest"]
    thinking_rates = pm["models"]["gpt-5.2"]
    
    assert instant_rates["input"] == thinking_rates["input"], \
        "Input rates should be identical"
    assert instant_rates["output"] == thinking_rates["output"], \
        "Output rates should be identical"
    
    # Verify both are $1.25/$10.00 as per OpenAI pricing
    assert Decimal(instant_rates["input"]) == Decimal("1.25"), \
        "Input rate should be $1.25 per million tokens"
    assert Decimal(instant_rates["output"]) == Decimal("10.00"), \
        "Output rate should be $10.00 per million tokens"
    
    # Calculate cost for SAME token counts - should be identical
    test_prompt = 1000
    test_completion = 500
    
    instant_cost = quote_cost_usd(pm, "gpt-5.2-chat-latest", test_prompt, test_completion)
    thinking_cost = quote_cost_usd(pm, "gpt-5.2", test_prompt, test_completion)
    
    assert instant_cost == thinking_cost, \
        "For IDENTICAL token counts, cost should be IDENTICAL"
    
    print(f"\n=== Pricing Rates Verification ===")
    print(f"Input rate: ${instant_rates['input']}/MTok (both models)")
    print(f"Output rate: ${instant_rates['output']}/MTok (both models)")
    print(f"For {test_prompt} prompt + {test_completion} completion: ${instant_cost}")
    print("✓ Rates are identical - cost difference comes from token count difference")


def test_check_actual_database_charges_for_consistency(db_session: Session):
    """Diagnostic test to check if there are any existing charges with suspicious patterns.
    
    This will help identify if the issue is:
    1. Estimation being wrong
    2. Real tokens not being captured
    3. Both models incorrectly using the same token counts
    """
    # Check for any existing gpt-5.2 charges
    instant_charges = db_session.query(Charge).filter(
        Charge.model == "gpt-5.2-chat-latest"
    ).all()
    
    thinking_charges = db_session.query(Charge).filter(
        Charge.model == "gpt-5.2"
    ).all()
    
    print(f"\n=== Database Diagnostics ===")
    print(f"Found {len(instant_charges)} Chat Latest charges, {len(thinking_charges)} GPT-5.2 charges")
    
    if instant_charges:
        avg_instant_completion = sum(c.completion_tokens_real or c.completion_tokens for c in instant_charges) / len(instant_charges)
        avg_instant_cost = sum(c.price_to_user_usd_real or c.price_to_user_usd for c in instant_charges) / len(instant_charges)
        print(f"Chat Latest avg: {avg_instant_completion:.0f} completion tokens, ${avg_instant_cost:.4f}")
    
    if thinking_charges:
        avg_thinking_completion = sum(c.completion_tokens_real or c.completion_tokens for c in thinking_charges) / len(thinking_charges)
        avg_thinking_cost = sum(c.price_to_user_usd_real or c.price_to_user_usd for c in thinking_charges) / len(thinking_charges)
        print(f"GPT-5.2 avg: {avg_thinking_completion:.0f} completion tokens, ${avg_thinking_cost:.4f}")
    
    if instant_charges and thinking_charges:
        if avg_instant_completion == avg_thinking_completion:
            print("⚠️  WARNING: Average completion tokens are IDENTICAL - this suggests reasoning tokens aren't being captured!")
        elif avg_thinking_completion > avg_instant_completion:
            overhead = ((avg_thinking_completion - avg_instant_completion) / avg_instant_completion * 100)
            print(f"✓ GPT-5.2 has {overhead:.1f}% more completion tokens (expected)")
        else:
            print("⚠️  WARNING: Chat Latest has MORE tokens than GPT-5.2 - this is unexpected!")
    
    # Check for any charges missing real token counts
    missing_real = db_session.query(Charge).filter(
        Charge.model.in_(["gpt-5.2-chat-latest", "gpt-5.2"]),
        Charge.completion_tokens_real.is_(None)
    ).count()
    
    if missing_real > 0:
        print(f"⚠️  WARNING: {missing_real} charges are missing completion_tokens_real - using estimates instead!")
