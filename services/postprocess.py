from __future__ import annotations

import asyncio
import json
import re
import logging
from typing import Any, AsyncIterator, Callable, Dict, Iterable, List, Optional, Tuple, Literal, cast

from config_loader import get_abuse_role, load_config
from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session
from restailor.models import Charge, UserBalance
from services.pricing import quote_cost_usd, apply_multiplier
from services.money import to_cents, format_usd

logger = logging.getLogger(__name__)


# Heuristic defaults (centralized constants)
MIN_RESUME_CHARS: int = 16
MIN_BULLETS: int = 5
OVERLAP_SAMPLE_STEP: int = 20
OVERLAP_WINDOW_SIZES: tuple[int, ...] = (100, 60, 30, 20, 10)


def _build_stopper(stop_markers: Iterable[str]) -> Tuple[re.Pattern[str], int]:
    markers = [m for m in (stop_markers or []) if isinstance(m, str) and m]
    if not markers:
        markers = ["### END"]
    escaped = [re.escape(m) for m in markers]
    pattern = re.compile("|".join(escaped))
    max_len = max(len(m) for m in markers)
    return pattern, max_len


def _overlap_chars(s: str, refs: List[str]) -> int:
    if not s or not refs:
        return 0
    total = 0
    blob = "\n".join(refs)
    L = len(s)
    step = OVERLAP_SAMPLE_STEP
    seen: set[Tuple[int, int]] = set()
    for i in range(0, L, step):
        for w in OVERLAP_WINDOW_SIZES:
            if i + w > L:
                continue
            seg = s[i : i + w]
            if seg in blob:
                total += w
                seen.add((i, i + w))
                break
    return total


def _looks_like_resume(text: str) -> bool:
    t = text.strip()
    if not t or t.startswith("{") or t.startswith("["):
        return False
    hits = 0
    for kw in ("summary", "experience", "education", "skills", "projects"):
        if re.search(rf"\b{kw}\b", t, re.I):
            hits += 1
    bullets = len(re.findall(r"^[-*•] ", t, re.M))
    return hits >= 2 or bullets >= MIN_BULLETS or len(t) >= MIN_RESUME_CHARS


async def wrap_stream(
    role: str,
    src_texts: List[str],
    agen: AsyncIterator[str],
    *,
    stop_markers: List[str] | None,
    echo_ratio_cap: float | None = None,
    max_quoted_chars: int | None = None,
    try_repair_json: Optional[Callable[[str], "asyncio.Future[str]"]] = None,
) -> AsyncIterator[Dict[str, Any]]:
    cfg = load_config() or {}
    role_l = (role or "").lower()
    if role_l in ("tailor", "fit", "judge"):
        role_lit = cast(Literal["tailor", "fit", "judge"], role_l)
    else:
        role_lit = cast(Literal["tailor", "fit", "judge"], "tailor")
    abuse_role = get_abuse_role(cfg, role_lit)
    if echo_ratio_cap is None:
        echo_ratio_cap = float((abuse_role or {}).get("max_echo_ratio", 0.8) or 0.8)
    if max_quoted_chars is None:
        max_quoted_chars = int((abuse_role or {}).get("max_quote_chars", 1200) or 1200)

    stopper, max_stop_len = _build_stopper(stop_markers or ["### END"])

    tail = ""
    buffer = ""
    tokens_out = 0
    clamped = False

    try:
        async for chunk in agen:
            s = str(chunk or "")
            if not s:
                continue
            combined = tail + s
            m = stopper.search(combined)
            if m:
                cut_upto = m.start()
                emit = combined[:cut_upto]
                start_in_chunk = max(0, len(tail))
                out_txt = emit[start_in_chunk:]
                if out_txt:
                    tokens_out += len(out_txt)
                    buffer += out_txt
                    yield {"type": "token", "text": out_txt}
                clamped = True
                break
            tokens_out += len(s)
            buffer += s
            yield {"type": "token", "text": s}
            if max_stop_len > 0:
                tail = combined[-max_stop_len:]
            if buffer and src_texts:
                quoted = _overlap_chars(buffer, src_texts)
                if max_quoted_chars and quoted > max_quoted_chars:
                    clamped = True
                    yield {"type": "token", "text": "[…]"}
                    break
                if echo_ratio_cap and len(buffer) > 500:
                    ratio = quoted / max(1, len(buffer))
                    if ratio >= echo_ratio_cap:
                        clamped = True
                        yield {"type": "token", "text": "[…]"}
                        break
    except asyncio.TimeoutError as te:
        raise te
    except Exception:
        raise
    finally:
        try:
            await agen.aclose()  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("agen.aclose failed: %r", e)

    result_txt = buffer
    if role_l == "tailor":
        if not _looks_like_resume(result_txt):
            yield {"type": "done", "status": "failed", "error": "schema_tailor", "clamped": clamped, "tokens_out_streamed": tokens_out}
            return
        yield {"type": "done", "status": "completed", "clamped": clamped, "tokens_out_streamed": tokens_out}
        return
    if role_l in ("fit", "judge"):
        def _valid_json(t: str) -> bool:
            try:
                json.loads(t)
                return True
            except Exception:
                return False
        if _valid_json(result_txt):
            yield {"type": "done", "status": "completed", "clamped": clamped, "tokens_out_streamed": tokens_out}
            return
        repaired_txt = None
        if try_repair_json is not None:
            try:
                repaired_txt = await try_repair_json(result_txt)
            except Exception:
                repaired_txt = None
        if repaired_txt and _valid_json(repaired_txt):
            extra = "\n\n" + repaired_txt
            tokens_out += len(extra)
            yield {"type": "token", "text": extra}
            yield {"type": "done", "status": "completed", "clamped": clamped, "tokens_out_streamed": tokens_out}
            return
        yield {"type": "done", "status": "failed", "error": "schema_invalid", "clamped": clamped, "tokens_out_streamed": tokens_out}
        return
    yield {"type": "done", "status": "completed", "clamped": clamped, "tokens_out_streamed": tokens_out}


def record_charge_for_job(
    session: Session,
    *,
    user_id: int | None,
    job_id: Any,
    request_type: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    price_map: dict,
    pricing_version: int | str,
    output_models: int | None = None,
    input_models: int | None = None,
    prompt_tokens_real: int | None = None,
    completion_tokens_real: int | None = None,
    token_estimation_method: str | None = None,
) -> None:
    """Persist Charge & decrement balance.

    Rules:
      - Always store heuristic (estimated) tokens/cost in cost_usd / price_to_user_usd.
      - Only populate *_real columns (tokens & cost) when BOTH real prompt & completion tokens provided.
      - Debit user balance using real price only when both sides real; otherwise use estimate.
      - token_estimation_method becomes 'provider_usage' only if real billing used.
    Idempotent per job_id.
    """
    import logging as _log
    _lg = _log.getLogger(__name__)
    try:
        _lg.info({"evt": "charge_attempt_start", "job_id": str(job_id), "user_id": int(user_id) if user_id else None, "request_type": request_type, "provider": provider, "model": model})
    except Exception:
        pass
    if not user_id:
        try:
            _lg.info({"evt": "charge_skip_no_user", "job_id": str(job_id)})
        except Exception:
            pass
        return
    # Idempotency check
    exists = session.query(Charge).filter(Charge.job_id == job_id).first() is not None
    if exists:
        try:
            _lg.info({"evt": "charge_skip_exists", "job_id": str(job_id)})
        except Exception:
            pass
        return

    # Parse real tokens (don't partially mix for billing)
    real_in: int | None = None
    real_out: int | None = None
    try:
        if prompt_tokens_real is not None and prompt_tokens_real >= 0:
            real_in = int(prompt_tokens_real)
        if completion_tokens_real is not None and completion_tokens_real >= 0:
            real_out = int(completion_tokens_real)
    except Exception:
        real_in = None
        real_out = None

    # Estimated baseline (always recorded)
    est_in = int(prompt_tokens or 0)
    est_out = int(completion_tokens or 0)
    est_cost = quote_cost_usd(price_map, model, est_in, est_out)
    multiplier_val = Decimal(price_map.get("multiplier", Decimal("1")))
    est_price = apply_multiplier(est_cost, multiplier_val)

    # Determine real token state
    real_complete = (real_in is not None) and (real_out is not None)
    real_partial = (not real_complete) and ((real_in is not None) or (real_out is not None))
    if real_complete:
        # mypy/pyright: real_in/out are not None inside this block
        rin = int(real_in)  # type: ignore[arg-type]
        rout = int(real_out)  # type: ignore[arg-type]
        real_cost = quote_cost_usd(price_map, model, rin, rout)
        real_price = apply_multiplier(real_cost, multiplier_val)
    else:
        real_cost = None
        real_price = None

    # Test flag
    _is_test = False
    try:
        from restailor.test_flags import is_automated_test_run as _is_auto
        if _is_auto():
            _is_test = True
    except Exception:
        _is_test = False

    # Model counts (guard rails)
    try:
        _out = int(output_models) if output_models is not None else 1
    except Exception:
        _out = 1
    if _out < 1:
        _out = 1
    try:
        _in = int(input_models) if input_models is not None else 0
    except Exception:
        _in = 0
    if _in < 0:
        _in = 0

    effective_method = token_estimation_method
    if real_complete:
        effective_method = "provider_usage"

    ch = Charge(
        user_id=int(user_id),
        job_id=job_id,
        request_type=str(request_type),
        provider=str(provider),
        model=str(model),
        output_models=_out,
        input_models=_in,
        prompt_tokens=est_in,
        completion_tokens=est_out,
        cost_usd=est_cost,
        price_to_user_usd=est_price,
        cost_usd_real=real_cost,
        price_to_user_usd_real=real_price,
        currency=str(price_map.get("currency", "USD")),
        pricing_version=int(str(pricing_version or 1)),
        is_test=_is_test,
        # Persist partial real tokens for analytics even if not billing from them
        prompt_tokens_real=(int(prompt_tokens_real) if prompt_tokens_real is not None else None),
        completion_tokens_real=(int(completion_tokens_real) if completion_tokens_real is not None else None),
        token_estimation_method=(str(effective_method) if effective_method else None),
    is_partial_real_tokens=bool(real_partial),
    multiplier_used=multiplier_val,
    )
    try:
        session.add(ch)
    except Exception as ex:
        try:
            _lg.warning({"evt": "charge_add_failed", "job_id": str(job_id), "err": str(ex)})
        except Exception:
            pass
        return

    # Debit: prefer real price only when full real pair
    debit_cents = to_cents(real_price if real_price is not None else est_price)
    billing_method = "real_tokens" if real_complete else "estimated_tokens"
    
    ub = session.get(UserBalance, int(user_id))
    if ub is None:
        ub = UserBalance(user_id=int(user_id), balance_cents=0)
        try:
            setattr(ub, "is_test", bool(_is_test))
        except Exception as e:
            logger.debug("set UserBalance.is_test failed: %r", e)
        session.add(ub)
    ub.balance_cents = int((ub.balance_cents or 0) - debit_cents)
    ub.updated_at = func.now()
    try:
        session.flush()
        try:
            _lg.info({
                "evt": "charge_persisted",
                "job_id": str(job_id),
                "user_id": int(user_id),
                "billing_method": billing_method,
                "prompt_tokens_est": est_in,
                "completion_tokens_est": est_out,
                "prompt_tokens_real": real_in if real_complete else None,
                "completion_tokens_real": real_out if real_complete else None,
                "price_est_usd": str(est_price),
                "price_real_usd": str(real_price) if real_price is not None else None,
                "debit_cents": int(debit_cents),
                "token_estimation_method": str(effective_method) if effective_method else None,
            })
        except Exception:
            pass
    except Exception as ex:
        try:
            _lg.warning({"evt": "charge_flush_failed", "job_id": str(job_id), "err": str(ex)})
        except Exception:
            pass
