"""Arq worker configuration and tasks."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional, Dict
import os

from arq.connections import RedisSettings
from restailor.app_config import CONFIG
from restailor.constants import MILLISECONDS_PER_SECOND
from services.analytics_job_snapshot import rebuild_snapshot_state
import os
from arq import cron
import sqlalchemy as sa
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ============================================================================
# Coalescing Constants
# ============================================================================
# These control how aggressively we batch streaming output to Redis
COALESCE_MS_MIN = 20        # Minimum coalescing delay (milliseconds)
COALESCE_MS_MAX = 500       # Maximum coalescing delay (milliseconds)
COALESCE_MS_DEFAULT = 100   # Default coalescing delay (milliseconds)
COALESCE_BYTES_MIN = 256    # Minimum buffer size before flush
COALESCE_BYTES_MAX = 8192   # Maximum buffer size before flush
COALESCE_BYTES_DEFAULT = 384  # Default buffer size (~3-5 sentences)

# Small shared helpers
def _get_env_bool(name: str, default: bool = False) -> bool:
    try:
        v = (os.getenv(name) or "").strip().lower()
        if v in ("1", "true", "yes", "y", "on"):
            return True
        if v in ("0", "false", "no", "n", "off"):
            return False
        return bool(default)
    except Exception:
        return bool(default)


def _get_env_int(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip())
    except Exception:
        return int(default)


def _chars_to_tokens(n: int) -> int:
    """Heuristic: ~4 chars per token with minimum 1 (matches prior usage).
    
    DEPRECATED: Use services.token_estimation.estimate_tokens() for better accuracy.
    This function remains for backwards compatibility with existing code.
    """
    try:
        return max(1, int(n / 4))
    except Exception:
        return max(1, n)


# Shared: compute external_cancel behavior once
def _make_external_cancel(redis, job_id: str, ignore_cancel_env: bool):
    """Return a coroutine function that checks cancel flag unless ignore is set.

    This mirrors prior semantics: when RT_IGNORE_CANCEL is true, streaming ignores
    external cancel and lets the request complete, but we still expose rt_ignore_cancel in meta.
    """
    async def _fn() -> bool:
        if ignore_cancel_env:
            return False
        try:
            v = await redis.get(f"cancel:{job_id}")  # type: ignore[attr-defined]
            return bool(v)
        except Exception:
            return False
    return _fn


# Shared: streaming coalescer for Redis buffers and meta updates
class Coalescer:
    def __init__(self, *, redis, meta_key: str, buf_key: str, t_start: float, tokens_in: int,
                 rt_coalesce_ms: int, rt_coalesce_bytes: int) -> None:
        self.redis = redis
        self.meta_key = meta_key
        self.buf_key = buf_key
        self.t_start = t_start
        self.tokens_in = int(tokens_in)
        self.rt_ms = int(rt_coalesce_ms)
        self.rt_bytes = int(rt_coalesce_bytes)
        self.buf: list[str] = []
        self.buf_bytes = 0
        self.last_flush = time.perf_counter()
        self.total = 0

    async def append(self, chunk: str) -> None:
        if not chunk:
            return
        self.buf.append(chunk)
        try:
            self.buf_bytes += len(chunk.encode("utf-8"))
        except Exception:
            self.buf_bytes += len(chunk)

    async def flush(self, *, force: bool = False) -> int:
        if self.buf_bytes <= 0 and not force:
            return self.total
        if not force:
            if self.buf_bytes < self.rt_bytes and ((time.perf_counter() - self.last_flush) * MILLISECONDS_PER_SECOND) < self.rt_ms:
                return self.total
        data = "".join(self.buf)
        pending = self.buf_bytes
        self.buf.clear(); self.buf_bytes = 0; self.last_flush = time.perf_counter()
        if not data:
            return self.total
        now_ts = time.time(); new_guess = self.total + pending
        import json as _json
        try:
            new_len = await self.redis.append(self.buf_key, data)  # type: ignore[attr-defined]
            try:
                self.total = int(new_len or new_guess)
            except Exception:
                self.total = new_guess
            await self.redis.set(self.meta_key, _json.dumps({
                "state": "running",
                "bytes": self.total,
                "updated_at": now_ts,
                "t_start": self.t_start,
                "tokens_in": self.tokens_in,
                "tokens_out_streamed": int(_chars_to_tokens(max(0, self.total))),
            }))  # type: ignore[attr-defined]
            return self.total
        except Exception:
            # Best-effort fallback path
            try:
                cur = await self.redis.get(self.buf_key)  # type: ignore[attr-defined]
                s = (cur.decode("utf-8", errors="ignore") if isinstance(cur, (bytes, bytearray)) else (cur or ""))
            except Exception:
                s = ""
            s2 = s + data
            try:
                await self.redis.set(self.buf_key, s2)  # type: ignore[attr-defined]
            except Exception:
                pass
            self.total = len(s2.encode("utf-8"))
            try:
                await self.redis.set(self.meta_key, _json.dumps({
                    "state": "running",
                    "bytes": self.total,
                    "updated_at": now_ts,
                    "t_start": self.t_start,
                    "tokens_in": self.tokens_in,
                    "tokens_out_streamed": int(_chars_to_tokens(max(0, self.total))),
                }))  # type: ignore[attr-defined]
            except Exception:
                pass
            return self.total

# Helper: resolve real provider token usage (prompt, completion) for a job.
# Attempts in-memory retrieval via services.llm.get_usage_for_job then best-effort
# Redis fallback (mirrors existing logic in one patched branch) to avoid future drift.
def _resolve_real_usage(job_id: str, ctx: Any) -> tuple[int | None, int | None]:  # type: ignore[override]
    """Synchronous facade returning cached / provider real token usage.

    Avoids run_until_complete on a running loop; if Redis fetch is needed inside
    an event loop, schedule a task and ignore if not immediately available.
    """
    try:
        from services.llm import get_usage_for_job  # local import to avoid cycles at module load
    except Exception:  # pragma: no cover
        return (None, None)
    real_p, real_c = get_usage_for_job(str(job_id))
    if real_p is not None or real_c is not None:
        return (real_p, real_c)
    # Redis fallback only if both None
    try:  # pragma: no cover - best effort
        r = ctx.get("redis") if isinstance(ctx, dict) else None
        if r:
            import json as _json
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            async def _fetch():
                try:
                    data = await r.get(f"usage:{job_id}")  # type: ignore[attr-defined]
                    if not data:
                        return
                    try:
                        if isinstance(data, (bytes, bytearray)):
                            data_str = data.decode("utf-8", errors="ignore")
                        else:
                            data_str = data
                        obj = _json.loads(data_str)
                        rp = obj.get("p")
                        rc = obj.get("c")
                        return rp, rc
                    except Exception:
                        return
                except Exception:
                    return
            result = None
            if loop and loop.is_running():
                fut = asyncio.ensure_future(_fetch())
                if fut.done():
                    result = fut.result()
            else:
                # standalone loop
                result = asyncio.run(_fetch())
            if result:
                rp, rc = result
                try: real_p = int(rp) if rp is not None else None
                except Exception: real_p = None  # type: ignore[assignment]
                try: real_c = int(rc) if rc is not None else None
                except Exception: real_c = None  # type: ignore[assignment]
    except Exception:
        pass
    return (real_p, real_c)

# Load .env for worker environment
try:
    load_dotenv()
except Exception as e:
    logger.debug("load_dotenv() failed: %r", e)

# Merge base global timeouts with provider/model-specific overrides.
def _merge_timeouts(cfg: dict[str, Any] | Any, provider: str, model: str) -> dict[str, Any]:
    try:
        base = dict((cfg.get("timeouts", {}) or {}))  # type: ignore[attr-defined]
    except Exception:
        base = {}
    try:
        prov = (provider or "").lower()
        tb = (cfg.get("timeouts_model", {}) or {}).get(prov, {})  # type: ignore[index]
        if isinstance(tb, dict):
            over = tb.get(model) or tb.get((model or "").lower())
            if isinstance(over, dict):
                base.update(over)
    except Exception as _ex:
        logger.debug("_merge_timeouts failed: %r", _ex)
    return base


async def tailor_resume(
    ctx: dict[str, Any],
    job_id: str,
    provider: Optional[str] = None,
    model_id: Optional[str] = None,
) -> str:
    """Tailor a resume (single model) with streaming.

    Streams model output into Redis (buf + meta keys), tracks token estimates,
    and persists final tailored markdown and charge rows. Returns "OK" or a
    status string for special conditions (cancellation, missing job, etc.).
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import select, func, cast, Text as _Text, bindparam as _bind
    from restailor.db import SessionLocal, get_pii_key
    from restailor.models import Job, JobOutput
    from services.llm import stream_model, abort_job, StallBeforeFirstByte, get_usage_for_job
    from services.pricing import load_price_map
    from services.postprocess import record_charge_for_job
    from restailor.app_config import CONFIG as _CFG
    from config_loader import build_gen_params
    from datetime import datetime

    db: Session = SessionLocal()
    start = time.perf_counter()
    start = time.perf_counter()
    # Predefine job variable to satisfy static analyzers after refactors removing combined flow.
    job = None  # type: ignore[assignment]
    try:
        # Resolve Job and mark processing
        try:
            pk = uuid.UUID(job_id)  # type: ignore
        except Exception:
            pk = job_id  # type: ignore
        job = db.get(Job, pk)
        if job:
            job.status = "processing"
            job.job_flow = job.job_flow or "tailor"
            db.commit()

        # Decrypt inputs
        pii_key = get_pii_key()
        row = db.execute(
            select(
                func.pgp_sym_decrypt(Job.resume_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("resume_text"),
                func.pgp_sym_decrypt(Job.jd_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("jd_text"),
            ).where(Job.id == pk)
        ).first()
        if not row:
            try:
                logger.warning({"evt": "worker_skip_missing_job", "task": "tailor_resume", "job_id": str(job_id)})
            except Exception:
                pass
            return "SKIP_MISSING_JOB"
        resume_text = row.resume_text or ""
        jd_text = row.jd_text or ""

        # Build prompts
        from restailor.prompt_wrap import build_prompts
        sys_prompt, user_prompt, end_marker = build_prompts(_CFG, "tailor", resume_text, jd_text, str(job_id))
        try:
            now = datetime.now()
            sys_prompt = (
                (sys_prompt or "").replace("[[TODAY_ISO]]", now.strftime("%Y-%m-%d"))
                .replace("[[TODAY]]", now.strftime("%B %d, %Y"))
                .replace("[[CURRENT_YEAR]]", now.strftime("%Y"))
            )
        except Exception as e:
            logger.debug("date token inject failed: %r", e)

        # Estimate prompt tokens (~4 chars/token)
        tokens_in_est = _chars_to_tokens(len(sys_prompt) + len(user_prompt))

        # Redis helpers
        redis = ctx.get("redis")
        if redis is None:
            class _Null:
                async def set(self, *a, **k): pass
                async def get(self, *a, **k): return None
                async def append(self, *a, **k): return 0
                async def expire(self, *a, **k): pass
                async def delete(self, *a, **k): pass
                def pipeline(self, *a, **k):
                    class P:
                        def append(self, *a, **k): return self
                        def set(self, *a, **k): return self
                        async def execute(self): return [0, True]
                    return P()
            redis = _Null()

        meta_key = f"job:{job_id}:meta"
        buf_key = f"job:{job_id}:buf"
        art_key = f"job:{job_id}:artifact"

        async def _set_meta(**fields: Any) -> None:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                data: dict[str, Any] = {}
                if cur:
                    try:
                        data = _json.loads(cur if isinstance(cur, str) else cur.decode("utf-8", errors="ignore"))
                    except Exception:
                        data = {}
                data.update(fields)
                await redis.set(meta_key, _json.dumps(data))  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_set_meta failed: %r", e)

        async def _read_meta() -> dict[str, Any]:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                if not cur:
                    return {}
                if isinstance(cur, (bytes, bytearray)):
                    return _json.loads(cur.decode("utf-8", errors="ignore"))
                if isinstance(cur, str):
                    return _json.loads(cur)
                return {}
            except Exception:
                return {}

        async def _append(chunk: str) -> int:
            try:
                new_len = await redis.append(buf_key, chunk)  # type: ignore[attr-defined]
                return int(new_len or 0)
            except Exception:
                try:
                    cur = await redis.get(buf_key)  # type: ignore[attr-defined]
                    s = (cur.decode("utf-8", errors="ignore") if isinstance(cur, (bytes, bytearray)) else (cur or ""))
                except Exception:
                    s = ""
                s2 = s + (chunk or "")
                try:
                    await redis.set(buf_key, s2)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.debug("_append fallback set failed: %r", e)
                return len(s2.encode("utf-8"))

        async def _get_cancel() -> bool:
            try:
                v = await redis.get(f"cancel:{job_id}")  # type: ignore[attr-defined]
                return bool(v)
            except Exception:
                return False

        async def _expire_keys(ttl: int = 600) -> None:
            try:
                if hasattr(redis, "expire"):
                    await redis.expire(meta_key, ttl)  # type: ignore[attr-defined]
                    await redis.expire(buf_key, ttl)   # type: ignore[attr-defined]
                    await redis.expire(art_key, ttl)   # type: ignore[attr-defined]
                else:
                    cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                    if cur is not None and hasattr(redis, "setex"):
                        await redis.setex(meta_key, ttl, cur)  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_expire_keys failed: %r", e)

        # Metrics timeline
        try:
            _m0 = await _read_meta()
            t_enqueue = _m0.get("t_enqueue")
        except Exception:
            t_enqueue = None

        t_start = time.time()
        t_first_chunk = None
        t_cancel_click = None
        t_cancel_seen_job = None
        t_done = None

        # Initialize meta and local state
        await _set_meta(
            state="running",
            bytes=0,
            updated_at=t_start,
            t_start=t_start,
            rt_ignore_cancel=bool((os.getenv("RT_IGNORE_CANCEL") or "").strip() in ("1","true","yes")),
            tokens_in=int(tokens_in_est),
            tokens_out_streamed=0,
        )

        RT_COALESCE_MS = max(COALESCE_MS_MIN, min(COALESCE_MS_MAX, _get_env_int("RT_COALESCE_MS", COALESCE_MS_DEFAULT)))
        RT_COALESCE_BYTES = max(COALESCE_BYTES_MIN, min(COALESCE_BYTES_MAX, _get_env_int("RT_COALESCE_BYTES", COALESCE_BYTES_DEFAULT)))
        coalescer = Coalescer(
            redis=redis,
            meta_key=meta_key,
            buf_key=buf_key,
            t_start=t_start,
            tokens_in=int(tokens_in_est),
            rt_coalesce_ms=RT_COALESCE_MS,
            rt_coalesce_bytes=RT_COALESCE_BYTES,
        )

        # Build provider/model params and timeouts
        params = build_gen_params(_CFG, (provider or ""), "tailor", (model_id or ""))  # type: ignore[arg-type]
        user_full = user_prompt + "\n\n" + end_marker
        # Build timeouts using shared merge logic with per-model overrides
        try:
            timeouts = _merge_timeouts(_CFG, (provider or ""), (model_id or ""))
        except Exception:
            timeouts = {}

        # Streaming and cancel handling
        try:
            _ignore_cancel = _get_env_bool("RT_IGNORE_CANCEL", False)
            ext_cancel = (None if _ignore_cancel else _make_external_cancel(redis, job_id, _ignore_cancel))
            # Optional: disable external cancel for specific OpenAI models if configured
            try:
                if (provider or "").strip().lower() == "openai" and (model_id or "").strip().lower().startswith("gpt-5"):
                    ocfg = (((_CFG.get("providers", {}) or {}).get("openai", {}) or {}))
                    if bool(ocfg.get("gpt5_disable_external_cancel", True)):
                        ext_cancel = None
            except Exception as e:
                logger.debug("disable external cancel merge failed: %r", e)

            async for chunk in stream_model(
                provider=(provider or ""),
                model=(model_id or ""),
                system_prompt=sys_prompt,
                user_prompt=user_full,
                params=params,
                timeouts=timeouts,
                # Add dynamic end marker to client-side stop markers.
                stop_markers=[end_marker],
                job_id=job_id,
                external_cancel=ext_cancel,
            ):
                if (not _ignore_cancel) and ext_cancel is not None and await ext_cancel():
                    try:
                        await coalescer.flush(force=True)
                    except Exception as e:
                        logger.debug("flush on cancel failed: %r", e)
                    try:
                        abort_job(job_id)
                    except Exception as e:
                        logger.debug("abort_job failed: %r", e)
                    await _set_meta(state="cancelled", updated_at=time.time())
                    await _expire_keys()
                    if job:
                        try:
                            job.status = "failed"
                            try:
                                job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                            except Exception:
                                pass
                            db.commit()
                        except Exception:
                            db.rollback()
                    # Best-effort partial charge (no real usage captured yet on cancel path)
                    try:
                        m = await _read_meta()
                        prompt_tokens = int(m.get("tokens_in", 0) or 0)
                        completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                        pm = load_price_map()
                        if job is not None and getattr(job, "user_id", None):
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "tailor") or "tailor"),
                                provider=str(provider or ""),
                                model=str(model_id or ""),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                price_map=pm,
                                pricing_version=int(pm.get("version", 1)),
                                prompt_tokens_real=None,
                                completion_tokens_real=None,
                                token_estimation_method="heuristic_v1",
                            )
                            db.commit()
                    except Exception:
                        db.rollback()
                    return "CANCELED"

                # First chunk timestamp
                just_started = False
                c = (chunk or "")
                if t_first_chunk is None and c:
                    t_first_chunk = time.time()
                    await _set_meta(t_first_chunk=t_first_chunk)
                    just_started = True
                if c:
                    await coalescer.append(c)
                await coalescer.flush(force=just_started)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            try:
                abort_job(job_id)
            except Exception as e:
                logger.debug("abort_job on CancelledError failed: %r", e)
            await _set_meta(state="cancelled", failure_reason="canceled by user", updated_at=time.time())
            await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    db.commit()
                except Exception:
                    db.rollback()
            # Best-effort partial charge (no real usage captured yet on cancel path)
            try:
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                pm = load_price_map()
                if job is not None and getattr(job, "user_id", None):
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "tailor") or "tailor"),
                        provider=str(provider or ""),
                        model=str(model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=None,
                        completion_tokens_real=None,
                        token_estimation_method="heuristic_v1",
                    )
                    db.commit()
            except Exception:
                db.rollback()
            # Metrics best-effort
            t_done = time.time()
            try:
                logger.warning({
                    "evt": "cancel_metrics",
                    "job_id": str(job_id),
                    "provider": provider,
                    "model": model_id,
                    "t_enqueue": t_enqueue,
                    "t_start": t_start,
                    "t_first_chunk": t_first_chunk,
                    "t_done": t_done,
                })
            except Exception:
                pass
            return "CANCELED"
        except StallBeforeFirstByte:
            await _set_meta(state="failed", failure_reason="stream stalled before first token", updated_at=time.time())
            await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    db.commit()
                except Exception:
                    db.rollback()
            return "FAILED:STALL_BEFORE_FIRST"
        except asyncio.TimeoutError as ex:
            await _set_meta(state="failed", failure_reason="provider timeout", updated_at=time.time())
            await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                logger.warning({
                    "evt": "stall_timeout",
                    "job_id": str(job_id),
                    "provider": provider,
                    "model": model_id,
                    "t_enqueue": t_enqueue,
                    "t_start": t_start,
                    "t_first_chunk": t_first_chunk,
                    "error": str(ex),
                })
            except Exception:
                pass
            return "FAILED:STALL_TIMEOUT"

        # Finalize: cache artifact and persist DB
        try:
            await coalescer.flush(force=True)
        except Exception as e:
            logger.debug("final flush failed: %r", e)
        final_text = ""
        try:
            buf = await redis.get(buf_key)  # type: ignore[attr-defined]
            if buf:
                final_text = buf.decode("utf-8", errors="ignore") if isinstance(buf, (bytes, bytearray)) else str(buf)
        except Exception as e:
            logger.debug("read final buffer failed: %r", e)
        try:
            await redis.set(art_key, final_text)  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("set final artifact failed: %r", e)
        if job:
            try:
                from restailor.privacy import should_persist_user_content
                from restailor.models import User as _U
                u = db.get(_U, getattr(job, "user_id", None)) if getattr(job, "user_id", None) else None
                persist_ok = bool(u and should_persist_user_content(u))
            except Exception as e:
                logger.debug("persist check failed, defaulting to persist: %r", e)
                persist_ok = True
            if persist_ok:
                key = get_pii_key()
                out = JobOutput(job_id=pk, type="tailored")
                db.add(out); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value=(final_text or ""), type_=sa.Text),
                        sa.bindparam("k", value=key, type_=sa.Text),
                        sa.bindparam("id", value=str(out.id)),
                    )
                )
            job.status = "completed"
            job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
            db.commit()
            try:
                pm = load_price_map()
                try:
                    m = await _read_meta()
                except Exception:
                    m = {}
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                real_p, real_c = get_usage_for_job(str(job_id))
                if real_p is None and real_c is None:
                    try:
                        r = ctx.get("redis") if isinstance(ctx, dict) else None
                        if r:
                            data = await r.get(f"usage:{job_id}")  # type: ignore[attr-defined]
                            if data:
                                import json as _json
                                try:
                                    if isinstance(data, (bytes, bytearray)):
                                        data_str = data.decode("utf-8", errors="ignore")
                                    else:
                                        data_str = data
                                    obj = _json.loads(data_str)
                                    real_p = obj.get("p")
                                    real_c = obj.get("c")
                                    logger.warning({"evt": "usage_fetch_redis", "job_id": str(job_id), "prompt_tokens_real": real_p, "completion_tokens_real": real_c})
                                except Exception as _je:
                                    logger.debug({"evt": "usage_fetch_redis_parse_fail", "job_id": str(job_id), "err": str(_je)})
                    except Exception as ex:
                        logger.debug({"evt": "usage_fetch_redis_fail", "job_id": str(job_id), "err": str(ex)})
                if job is not None and getattr(job, "user_id", None):
                    real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "tailor") or "tailor"),
                        provider=str(provider or ""),
                        model=str(model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=real_p,
                        completion_tokens_real=real_c,
                        token_estimation_method="heuristic_v1",
                    )
                    db.commit()
            except Exception:
                db.rollback()
        t_done = time.time()
        await _set_meta(state="succeeded", updated_at=t_done, artifact_key=art_key)
        await _expire_keys()
        try:
            logger.warning({
                "evt": "cancel_metrics",
                "job_id": str(job_id),
                "provider": provider,
                "model": model_id,
                "t_enqueue": t_enqueue,
                "t_start": t_start,
                "t_first_chunk": t_first_chunk,
                "t_done": t_done,
            })
        except Exception:
            pass
        return "OK"
    except Exception:
        if 'job' in locals() and job:
            try:
                job.status = "failed"
                db.commit()
            except Exception:
                db.rollback()
        raise
    finally:
        # Fallback: ensure latency is set if still NULL
        try:
            try:
                _pk = uuid.UUID(job_id)
            except Exception:
                _pk = job_id  # type: ignore
            from restailor.models import Job as _Job
            jrow = db.get(_Job, _pk)
            if jrow is not None and (getattr(jrow, "latency_ms", None) is None):
                try:
                    jrow.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            pass
        db.close()


# --- New tasks: job fit and judge-only ---
async def check_job_fit(
    ctx: dict[str, Any],
    job_id: str,
    provider: Optional[str],
    model_id: Optional[str],
) -> str:
    from sqlalchemy.orm import Session
    from sqlalchemy import select, func, cast, Text as _Text, bindparam as _bind
    from restailor.db import SessionLocal, get_pii_key
    from restailor.models import Job, JobOutput
    from restailor.app_config import CONFIG as _CFG
    from services.pricing import load_price_map
    from services.postprocess import record_charge_for_job

    db: Session = SessionLocal()
    start = time.perf_counter()
    try:
        # Best-effort: clear any stale cancel flag so a new job doesn't inherit it
        try:
            r = ctx.get("redis") if isinstance(ctx, dict) else None
            if r is not None and hasattr(r, "get"):
                if await r.get(f"cancel:{job_id}"):
                    try:
                        await r.delete(f"cancel:{job_id}")
                    except Exception as e:
                        logger.debug("clear stale cancel flag (fit) failed: %r", e)
        except Exception as e:
            logger.debug("fit: cancel flag check failed: %r", e)

        # Fetch and decrypt resume/jd via pgcrypto
        try:
            pk = uuid.UUID(job_id)
        except Exception:
            pk = job_id  # type: ignore
        pii_key = get_pii_key()
        row = db.execute(
            select(
                func.pgp_sym_decrypt(Job.resume_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("resume_text"),
                func.pgp_sym_decrypt(Job.jd_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("jd_text"),
            ).where(Job.id == pk)
        ).first()
        if not row:
            logger.warning({
                "evt": "worker_skip_missing_job",
                "task": "check_job_fit",
                "job_id": str(job_id),
            })
            return "SKIP_MISSING_JOB"
        resume_text = row.resume_text or ""
        jd_text = row.jd_text or ""

        # Build prompts for streaming using the same wrapper as tailor
        from restailor.prompt_wrap import build_prompts
        sys_prompt, user_prompt, end_marker = build_prompts(_CFG, "fit", resume_text or "", jd_text or "", str(job_id))
        # Inject date tokens into system prompt (align with tailor/judge flows)
        try:
            from datetime import datetime as _dt
            now = _dt.now()
            sys_prompt = (
                (sys_prompt or "").replace("[[TODAY_ISO]]", now.strftime("%Y-%m-%d"))
                .replace("[[TODAY]]", now.strftime("%B %d, %Y"))
                .replace("[[CURRENT_YEAR]]", now.strftime("%Y"))
            )
        except Exception as e:
            logger.debug("date token inject (fit) failed: %r", e)
        # Redis + meta helpers (same pattern as tailor_resume)
        redis = ctx.get("redis") if isinstance(ctx, dict) else None
        if redis is None:
            class _Null:
                async def set(self, *a, **k): pass
                async def get(self, *a, **k): return None
                async def append(self, *a, **k): return 0
            redis = _Null()
        meta_key = f"job:{job_id}:meta"
        buf_key = f"job:{job_id}:buf"
        art_key = f"job:{job_id}:artifact"

        async def _set_meta(**fields: Any) -> None:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                data: dict[str, Any] = {}
                if cur:
                    try:
                        data = _json.loads(cur if isinstance(cur, str) else cur.decode("utf-8", errors="ignore"))
                    except Exception:
                        data = {}
                data.update(fields)
                await redis.set(meta_key, _json.dumps(data))  # type: ignore[attr-defined]
            except Exception:
                logger.debug("_set_meta (fit) failed to write", exc_info=True)

        async def _read_meta() -> dict[str, Any]:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                if not cur:
                    return {}
                if isinstance(cur, (bytes, bytearray)):
                    return _json.loads(cur.decode("utf-8", errors="ignore"))
                if isinstance(cur, str):
                    return _json.loads(cur)
                return {}
            except Exception:
                return {}

        async def _expire_keys(ttl: int = 600) -> None:
            try:
                if hasattr(redis, "expire"):
                    await redis.expire(meta_key, ttl)  # type: ignore[attr-defined]
                    await redis.expire(buf_key, ttl)   # type: ignore[attr-defined]
                    await redis.expire(art_key, ttl)   # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_expire_keys (fit) failed: %r", e)

        pk = uuid.UUID(job_id)
        job = db.get(Job, pk)
        if job:
            job.status = "processing"
            job.job_flow = job.job_flow or "fit"
            try:
                db.commit()
            except Exception:
                # Likely partial-unique conflict if another active job exists; finalize with a clear message
                db.rollback()
                try:
                    key = get_pii_key()
                    job = db.get(Job, pk)
                    if job:
                        job.status = "failed"
                        out = JobOutput(job_id=pk, type="fit")
                        db.add(out); db.flush()
                        db.execute(
                            sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                            .bindparams(
                                sa.bindparam("v", value="(fit canceled: another active job exists)", type_=sa.Text),
                                sa.bindparam("k", value=key, type_=sa.Text),
                                sa.bindparam("id", value=str(out.id)),
                            )
                        )
                        db.commit()
                except Exception:
                    db.rollback()
                return "CANCELED"
        # If canceled before starting the provider call, honor it quickly
        try:
            db.refresh(job)
        except Exception as e:
            logger.debug("early cancel check (bench rank) failed: %r", e)
        if job is not None and getattr(job, "status", None) in ("failed", "canceling"):
            # Finalize with a message so SSE emits a helpful terminal event
            try:
                key = get_pii_key()
                job.status = "failed"
                try:
                    job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                except Exception:
                    pass
                out = JobOutput(job_id=pk, type="fit")
                db.add(out); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value="(fit canceled by user)", type_=sa.Text),
                        sa.bindparam("k", value=key, type_=sa.Text),
                        sa.bindparam("id", value=str(out.id)),
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
            return "CANCELED"

        # Streaming path with mid-flight cancel, now using shared Coalescer + cancel helper
        from services.llm import stream_model, abort_job, StallBeforeFirstByte
        from config_loader import build_gen_params
        params = build_gen_params(_CFG, (provider or ""), "fit", (model_id or ""))  # type: ignore[arg-type]
        # Provide timeouts and cancel ignore flag expected by stream_model
        try:
            timeouts = _merge_timeouts(_CFG, (provider or ""), (model_id or ""))  # per-model override restore
        except Exception:
            timeouts = {}
        _ignore_cancel = _get_env_bool("RT_IGNORE_CANCEL", False)
        user_full = (user_prompt or "") + "\n\n" + end_marker

        # Initialize meta and coalescing
        t_start = time.time()
        t_first_chunk = None
        # Rough prompt token estimate
        _tokens_in = _chars_to_tokens(len(sys_prompt or "") + len(user_prompt or ""))
        await _set_meta(
            state="running",
            bytes=0,
            updated_at=t_start,
            t_start=t_start,
            rt_ignore_cancel=bool((os.getenv("RT_IGNORE_CANCEL") or "").strip() in ("1","true","yes")),
            tokens_in=int(_tokens_in),
            tokens_out_streamed=0,
        )
        # Coalescer and external cancel helper
        RT_COALESCE_MS = max(COALESCE_MS_MIN, min(COALESCE_MS_MAX, _get_env_int("RT_COALESCE_MS", COALESCE_MS_DEFAULT)))
        RT_COALESCE_BYTES = max(COALESCE_BYTES_MIN, min(COALESCE_BYTES_MAX, _get_env_int("RT_COALESCE_BYTES", COALESCE_BYTES_DEFAULT)))
        coalescer = Coalescer(
            redis=redis,
            meta_key=meta_key,
            buf_key=buf_key,
            t_start=t_start,
            tokens_in=int(_tokens_in),
            rt_coalesce_ms=RT_COALESCE_MS,
            rt_coalesce_bytes=RT_COALESCE_BYTES,
        )
        external_cancel = _make_external_cancel(redis, job_id, _ignore_cancel)

        # Streaming fit generation using unified streaming layer
        try:
            async for chunk in stream_model(
                provider=(provider or ""),
                model=(model_id or ""),
                system_prompt=sys_prompt,
                user_prompt=user_full,
                params=params,
                timeouts=timeouts,
                stop_markers=[end_marker],
                job_id=job_id,
                external_cancel=(None if _ignore_cancel else external_cancel),
            ):
                if (not _ignore_cancel) and await external_cancel():
                    try:
                        abort_job(job_id)
                    except Exception as e:
                        logger.debug("abort_job (fit) during cancel failed: %r", e)
                    await coalescer.flush(force=True)
                    await _set_meta(state="cancelled", updated_at=time.time())
                    await _expire_keys()
                    if job:
                        try:
                            job.status = "failed"
                            try:
                                job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                            except Exception:
                                pass
                            db.commit()
                        except Exception:
                            db.rollback()
                    # Best-effort partial charge on cancel
                    try:
                        pm = load_price_map()
                        m = await _read_meta()
                        prompt_tokens = int(m.get("tokens_in", 0) or 0)
                        completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                        if job is not None and getattr(job, "user_id", None):
                            # Attempt to resolve real provider usage (prompt, completion)
                            real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "fit") or "fit"),
                                provider=str(provider or ""),
                                model=str(model_id or ""),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                price_map=pm,
                                pricing_version=int(pm.get("version", 1)),
                                prompt_tokens_real=real_p,
                                completion_tokens_real=real_c,
                                token_estimation_method="heuristic_v1",
                            )
                            db.commit()
                    except Exception:
                        db.rollback()
                    return "CANCELED"
                if t_first_chunk is None:
                    t_first_chunk = time.time()
                    await _set_meta(t_first_chunk=t_first_chunk)
                c = chunk or ""
                if c:
                    await coalescer.append(c)
                await coalescer.flush(force=(coalescer.total == 0))
                await asyncio.sleep(0)
        except StallBeforeFirstByte:
            await _set_meta(state="failed", updated_at=time.time())
            await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            # Best-effort charge even on stall
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "fit") or "fit"),
                        provider=str(provider or ""),
                        model=str(model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=real_p,
                        completion_tokens_real=real_c,
                        token_estimation_method="heuristic_v1",
                    )
                    db.commit()
            except Exception:
                db.rollback()
            return "FAILED:STALL_BEFORE_FIRST"
        except asyncio.CancelledError:
            try:
                abort_job(job_id)
            except Exception as e:
                logger.debug("abort_job on CancelledError (fit) failed: %r", e)
            await _set_meta(state="cancelled", updated_at=time.time())
            await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            return "CANCELED"

        # Finalize: flush and persist
        try:
            await coalescer.flush(force=True)
        except Exception as e:
            logger.debug("final flush (fit) failed: %r", e)
        final_text = ""
        try:
            buf = await redis.get(buf_key)  # type: ignore[attr-defined]
            if buf:
                final_text = buf.decode("utf-8", errors="ignore") if isinstance(buf, (bytes, bytearray)) else str(buf)
        except Exception as e:
            logger.debug("read final buffer (fit) failed: %r", e)
        try:
            await redis.set(art_key, final_text)  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("set final artifact (fit) failed: %r", e)
        if job:
            # Respect user's privacy preference: avoid persisting generated content if opted out.
            try:
                from restailor.privacy import should_persist_user_content
                from restailor.models import User as _U
                u = db.get(_U, getattr(job, "user_id", None)) if getattr(job, "user_id", None) else None
                persist_ok = bool(u and should_persist_user_content(u))
            except Exception as e:
                logger.debug("persist check failed, defaulting to persist: %r", e)
                persist_ok = True
            if persist_ok:
                key = get_pii_key()
                out = JobOutput(job_id=pk, type="fit")
                db.add(out); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value=(final_text or ""), type_=sa.Text),
                        sa.bindparam("k", value=key, type_=sa.Text),
                        sa.bindparam("id", value=str(out.id)),
                    )
                )
            # Always finalize status even if we skipped persistence
            job.status = "completed"
            try:
                job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
            except Exception:
                pass
            db.commit()
            # Record final charge (idempotent per job)
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "fit") or "fit"),
                        provider=str(provider or ""),
                        model=str(model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=real_p,
                        completion_tokens_real=real_c,
                        token_estimation_method="heuristic_chars_div4",
                    )
                    db.commit()
            except Exception as e:
                # Preserve job completion status but surface root cause
                logger.warning("charge.final_attempt_failed job=%s err_type=%s err_msg=%s", pk, type(e).__name__, str(e)[:200])
                db.rollback()
            # Guard: if still no Charge row, attempt a lightweight recovery charge using only estimated tokens
            try:
                if job is not None and getattr(job, "user_id", None):
                    from restailor.models import Charge as _Charge
                    exists = db.query(_Charge.id).filter(_Charge.job_id == pk).first() is not None
                    if not exists:
                        logger.warning("charge.guard_missing_detected job=%s attempting_recovery=1", pk)
                        try:
                            pm2 = load_price_map()
                        except Exception as e2:
                            logger.warning("charge.guard_load_price_map_failed job=%s err=%r", pk, e2)
                            pm2 = {"multiplier": 1, "currency": "USD", "version": 1, "models": {}}
                        try:
                            m2 = await _read_meta()
                        except Exception:
                            m2 = {}
                        pt2 = int((m2.get("tokens_in", 0) or 0))
                        ct2 = int((m2.get("tokens_out_streamed", 0) or 0))
                        try:
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "fit") or "fit"),
                                provider=str(provider or ""),
                                model=str(model_id or ""),
                                prompt_tokens=pt2,
                                completion_tokens=ct2,
                                price_map=pm2,
                                pricing_version=int(pm2.get("version", 1) if isinstance(pm2, dict) else 1),
                                prompt_tokens_real=None,
                                completion_tokens_real=None,
                                token_estimation_method="guard_recovery",
                            )
                            db.commit()
                            # Re-check
                            exists2 = db.query(_Charge.id).filter(_Charge.job_id == pk).first() is not None
                            if exists2:
                                logger.warning("charge.guard_recovery_success job=%s", pk)
                            else:
                                logger.error("charge.guard_recovery_failed_no_row job=%s", pk)
                        except Exception as e3:
                            db.rollback()
                            logger.error("charge.guard_recovery_exception job=%s err_type=%s err_msg=%s", pk, type(e3).__name__, str(e3)[:200])
            except Exception as e_guard:
                logger.error("charge.guard_outer_exception job=%s err_type=%s err_msg=%s", pk, type(e_guard).__name__, str(e_guard)[:200])
        await _set_meta(state="succeeded", updated_at=time.time(), artifact_key=art_key)
        await _expire_keys()
        return "OK"
    finally:
        # Fallback: ensure latency is set if still NULL
        try:
            try:
                _pk = uuid.UUID(job_id)
            except Exception:
                _pk = job_id  # type: ignore
            from restailor.models import Job as _Job
            jrow = db.get(_Job, _pk)
            if jrow is not None and (getattr(jrow, "latency_ms", None) is None):
                try:
                    jrow.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            pass
        db.close()


async def judge_only(
    ctx: dict[str, Any],
    job_id: str,
    judge_provider: Optional[str],
    judge_model_id: Optional[str],
) -> str:
    from sqlalchemy.orm import Session
    from sqlalchemy import select, func, cast, Text as _Text, bindparam as _bind
    from restailor.db import SessionLocal, get_pii_key
    from restailor.models import Job, JobOutput
    from services.pricing import load_price_map
    from services.postprocess import record_charge_for_job

    db: Session = SessionLocal()
    start = time.perf_counter()
    job: Any = None  # ensure defined for exception handling consistency
    try:
        # Best-effort: clear any stale cancel flag
        try:
            r = ctx.get("redis") if isinstance(ctx, dict) else None
            if r is not None and hasattr(r, "get"):
                if await r.get(f"cancel:{job_id}"):
                    try:
                        await r.delete(f"cancel:{job_id}")
                    except Exception as e:
                        logger.debug("clear stale cancel flag (judge_only) failed: %r", e)
        except Exception as e:
            logger.debug("judge_only: cancel flag check failed: %r", e)
        # Fetch and decrypt candidate, resume, jd (resume/jd may be empty in judge-only flow)
        try:
            pk = uuid.UUID(job_id)
        except Exception:
            pk = job_id  # type: ignore
        pii_key = get_pii_key()
        row = db.execute(
            select(
                func.pgp_sym_decrypt(Job.candidate_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("candidate_text"),
                func.pgp_sym_decrypt(Job.resume_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("resume_text"),
                func.pgp_sym_decrypt(Job.jd_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("jd_text"),
            ).where(Job.id == pk)
        ).first()
        if not row:
            try:
                logger.warning({
                    "evt": "worker_skip_missing_job",
                    "task": "judge_only",
                    "job_id": str(job_id),
                })
            except Exception:
                pass
            return "SKIP_MISSING_JOB"
        candidate_text = row.candidate_text or ""
        resume_text = row.resume_text or ""
        jd_text = row.jd_text or ""
        # Path instrumentation: explicit judge_only entry (helps distinguish from judge_ranking in logs)
        try:
            logger.info({
                "evt": "judge_path",
                "path": "judge_only",
                "job_id": str(job_id),
                "candidate_chars": len(candidate_text or ""),
                "has_base_resume": bool(resume_text.strip()),
                "has_jd": bool(jd_text.strip()),
            })
        except Exception:
            pass
        # Mark job as processing at start (align with tailor)
        job = db.get(Job, pk)
        if job:
            job.status = "processing"
            job.job_flow = job.job_flow or "judge"
            try:
                db.commit()
            except Exception:
                db.rollback()
        def _get_api_key(p: str) -> Optional[str]:
            secret_names = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "CLAUDE_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "xai": "GROK_API_KEY",
            }
            name = secret_names.get(p)
            if not name:
                return None
            key: Optional[str] = None
            try:
                import keyring  # type: ignore
                key = keyring.get_password("restailor", name)  # type: ignore
            except Exception:
                key = None
            if not key:
                import os
                key = os.getenv(name)
            return key

        # Streaming judge using the same loop as tailor_resume
        from restailor.app_config import CONFIG as _CFG
        from services.llm import stream_model, abort_job, StallBeforeFirstByte
        from config_loader import build_gen_params

        # Build judge rubric (system) and payload (user)
        from pathlib import Path
        from datetime import datetime
        def _load_judge_prompt() -> str:
            try:
                root = Path(__file__).resolve().parent
                text = (root / "prompts" / "judge.md").read_text(encoding="utf-8").strip()
            except Exception:
                return "You are a strict evaluator. Return clear scores and a concise analysis."
            try:
                now = datetime.now()
                return (text.replace("[[TODAY_ISO]]", now.strftime("%Y-%m-%d"))
                            .replace("[[TODAY]]", now.strftime("%B %d, %Y"))
                            .replace("[[CURRENT_YEAR]]", now.strftime("%Y")))
            except Exception:
                return text
        def _payload(eval_prompt: str) -> str:
            override = (
                "=== INSTRUCTIONS_OVERRIDE ===\n"
                "There is exactly 1 candidate resume.\n"
                "Use Mode 1: Single Resume Analysis.\n"
                "Refer generically to 'the resume' only.\n"
            )
            return (
                "=== RUBRIC ===\n" + eval_prompt + "\n\n"
                + override
                + "\n=== BASE_RESUME ===\n" + (resume_text or "")
                + "\n\n=== JOB_DESCRIPTION ===\n" + (jd_text or "")
                + "\n\n=== CANDIDATE_RESUME ===\n" + (candidate_text or "")
            )

        sys_prompt = _load_judge_prompt()
        user_prompt = _payload(sys_prompt)
        end_marker = "<<END>>"  # judge doesn't rely on a specific marker; keep simple
        user_full = user_prompt + "\n\n" + end_marker
        # Prompt token estimate (use shared helper)
        _tokens_in = _chars_to_tokens(len(sys_prompt or "") + len(user_full or ""))

        # Redis helpers
        redis = ctx.get("redis") if isinstance(ctx, dict) else None
        if redis is None:
            class _Null:
                async def set(self, *a, **k): pass
                async def get(self, *a, **k): return None
                async def append(self, *a, **k): return 0
            redis = _Null()
        meta_key = f"job:{job_id}:meta"
        buf_key = f"job:{job_id}:buf"
        art_key = f"job:{job_id}:artifact"

        async def _set_meta(**fields: Any) -> None:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                data: dict[str, Any] = {}
                if cur:
                    try:
                        data = _json.loads(cur if isinstance(cur, str) else cur.decode("utf-8", errors="ignore"))
                    except Exception:
                        data = {}
                data.update(fields)
                await redis.set(meta_key, _json.dumps(data))  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_set_meta (judge_only) failed: %r", e)

        async def _read_meta() -> dict[str, Any]:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                if not cur:
                    return {}
                if isinstance(cur, (bytes, bytearray)):
                    return _json.loads(cur.decode("utf-8", errors="ignore"))
                if isinstance(cur, str):
                    return _json.loads(cur)
                return {}
            except Exception:
                return {}

        async def _append(chunk: str) -> int:
            try:
                new_len = await redis.append(buf_key, chunk)  # type: ignore[attr-defined]
                return int(new_len or 0)
            except Exception:
                try:
                    cur = await redis.get(buf_key)  # type: ignore[attr-defined]
                    s = (cur.decode("utf-8", errors="ignore") if isinstance(cur, (bytes, bytearray)) else (cur or ""))
                except Exception:
                    s = ""
                s2 = s + (chunk or "")
                try:
                    await redis.set(buf_key, s2)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.debug("redis.set in _append (judge_only) failed: %r", e)
                return len(s2.encode("utf-8"))

        async def _expire_keys(ttl: int = 600) -> None:
            try:
                if hasattr(redis, "expire"):
                    await redis.expire(meta_key, ttl)  # type: ignore[attr-defined]
                    await redis.expire(buf_key, ttl)   # type: ignore[attr-defined]
                    await redis.expire(art_key, ttl)   # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_expire_keys (judge_only) failed: %r", e)

        # Init meta & coalescing (centralized helper)
        t_start = time.time(); t_first_chunk = None
        _ignore_cancel_env = _get_env_bool("RT_IGNORE_CANCEL", False)
        await _set_meta(
            state="running",
            bytes=0,
            updated_at=t_start,
            t_start=t_start,
            rt_ignore_cancel=_ignore_cancel_env,
            tokens_in=int(_tokens_in),
            tokens_out_streamed=0,
        )
        RT_COALESCE_MS = max(COALESCE_MS_MIN, min(COALESCE_MS_MAX, _get_env_int("RT_COALESCE_MS", COALESCE_MS_DEFAULT)))
        RT_COALESCE_BYTES = max(COALESCE_BYTES_MIN, min(COALESCE_BYTES_MAX, _get_env_int("RT_COALESCE_BYTES", COALESCE_BYTES_DEFAULT)))
        coalescer = Coalescer(
            redis=redis,
            meta_key=meta_key,
            buf_key=buf_key,
            t_start=t_start,
            tokens_in=int(_tokens_in),
            rt_coalesce_ms=RT_COALESCE_MS,
            rt_coalesce_bytes=RT_COALESCE_BYTES,
        )
        external_cancel = _make_external_cancel(redis, job_id, _ignore_cancel_env)

        # Streaming judge using unified streaming layer
        # Build generation params/timeouts similar to fit flow
        try:
            params = build_gen_params(_CFG, (judge_provider or ""), "judge", (judge_model_id or ""))  # type: ignore[arg-type]
        except Exception:
            params = {}
        try:
            timeouts = _merge_timeouts(_CFG, (judge_provider or ""), (judge_model_id or ""))  # per-model override restore
        except Exception:
            timeouts = {}
        try:
            async for chunk in stream_model(
                provider=(judge_provider or ''),
                model=(judge_model_id or ''),
                system_prompt=sys_prompt,
                user_prompt=user_full,
                params=params,
                timeouts=timeouts,
                stop_markers=[end_marker],
                job_id=job_id,
                external_cancel=(None if _ignore_cancel_env else external_cancel),
            ):
                if (not _ignore_cancel_env) and await external_cancel():
                    try:
                        abort_job(job_id)
                    except Exception as e:
                        logger.debug("abort_job during bench rank cancel failed: %r", e)
                    await coalescer.flush(force=True)
                    await _set_meta(state="cancelled", updated_at=time.time())
                    await _expire_keys()
                    if job:
                        try:
                            job.status = "failed"
                            try:
                                job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                            except Exception:
                                pass
                            db.commit()
                        except Exception:
                            db.rollback()
                    try:
                        pm = load_price_map()
                        m = await _read_meta()
                        prompt_tokens = int(m.get("tokens_in", 0) or 0)
                        completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                        if job is not None and getattr(job, "user_id", None):
                            try:
                                real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                            except Exception:
                                real_p, real_c = (None, None)
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                                provider=str(judge_provider or ""),
                                model=str(judge_model_id or ""),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                price_map=pm,
                                pricing_version=int(pm.get("version", 1)),
                                prompt_tokens_real=real_p,
                                completion_tokens_real=real_c,
                                token_estimation_method="heuristic_chars_div4",
                                output_models=1,
                                input_models=0,
                            )
                            db.commit()
                    except Exception:
                        db.rollback()
                    return "CANCELED"
                if t_first_chunk is None:
                    t_first_chunk = time.time(); await _set_meta(t_first_chunk=t_first_chunk)
                c = (chunk or "")
                if c:
                    await coalescer.append(c)
                await coalescer.flush(force=(coalescer.total == 0))
                await asyncio.sleep(0)
        except StallBeforeFirstByte:
            await _set_meta(state="failed", failure_reason="stream stalled before first token", updated_at=time.time()); await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                # Early billing block removed; nothing to do here now.
                pass
            except Exception:
                db.rollback()
            return "FAILED:STALL_BEFORE_FIRST"
        except asyncio.CancelledError:
            try:
                abort_job(job_id)
            except Exception as e:
                logger.debug("abort_job on CancelledError failed: %r", e)
            await _set_meta(state="cancelled", failure_reason="canceled by user", updated_at=time.time()); await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    try:
                        real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                    except Exception:
                        real_p, real_c = (None, None)
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                        provider=str(judge_provider or ""),
                        model=str(judge_model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=real_p,
                        completion_tokens_real=real_c,
                        token_estimation_method="heuristic_chars_div4",
                        output_models=1,
                        input_models=0,
                    )
                    db.commit()
            except Exception:
                db.rollback()
            return "CANCELED"

        # Finalize: persist judge narrative and mark job completed
        try:
            await coalescer.flush(force=True)
        except Exception as e:
            logger.debug("final flush (section) failed: %r", e)
        final_text = ""
        try:
            buf = await redis.get(buf_key)  # type: ignore[attr-defined]
            if buf:
                final_text = buf.decode("utf-8", errors="ignore") if isinstance(buf, (bytes, bytearray)) else str(buf)
        except Exception as e:
            logger.debug("read final buffer (section) failed: %r", e)
        try:
            await redis.set(art_key, final_text)  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("set final artifact (section) failed: %r", e)
        if job:
            # Respect privacy preference: skip persisting judge narrative if opted-out.
            try:
                from restailor.privacy import should_persist_user_content
                from restailor.models import User as _U
                u = db.get(_U, getattr(job, "user_id", None)) if getattr(job, "user_id", None) else None
                persist_ok = bool(u and should_persist_user_content(u))
            except Exception:
                persist_ok = True
            if persist_ok:
                key2 = get_pii_key()
                out_j = JobOutput(job_id=pk, type="judge")
                db.add(out_j); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value=(final_text or ""), type_=sa.Text),
                        sa.bindparam("k", value=key2, type_=sa.Text),
                        sa.bindparam("id", value=str(out_j.id)),
                    )
                )
            try:
                job.status = "completed"
                try:
                    job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                except Exception:
                    pass
                db.commit()
            except Exception:
                db.rollback()
            # Record final charge (idempotent per job)
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    try:
                        real_p, real_c = _resolve_real_usage(str(job_id), ctx)
                    except Exception:
                        real_p, real_c = (None, None)
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                        provider=str(judge_provider or ""),
                        model=str(judge_model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=real_p,
                        completion_tokens_real=real_c,
                        token_estimation_method="heuristic_chars_div4",
                        output_models=1,
                        input_models=0,
                    )
                    db.commit()
            except Exception:
                db.rollback()
        await _set_meta(state="succeeded", updated_at=time.time(), artifact_key=art_key)
        return "OK"
    except Exception:
        # Avoid referencing possibly unbound local; fetch job row directly for failure marking.
        try:
            try:
                pk_fail = uuid.UUID(job_id)
            except Exception:
                pk_fail = job_id  # type: ignore[assignment]
            job_row = db.get(Job, pk_fail)
            if job_row is not None:
                job_row.status = "failed"
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        try:  # best-effort meta annotation; ignore if helper unavailable in this scope
            if ' _set_meta' or '_set_meta' in locals():  # type: ignore[truthy-function]
                try:
                    await _set_meta(state="failed", failure_reason="unexpected exception in judge_only", updated_at=time.time())  # type: ignore[name-defined]
                except Exception:
                    pass
        except Exception:
            pass
        raise
    finally:
        # Fallback: ensure latency is set if still NULL
        try:
            try:
                _pk = uuid.UUID(job_id)
            except Exception:
                _pk = job_id  # type: ignore
            from restailor.models import Job as _Job
            jrow = db.get(_Job, _pk)
            if jrow is not None and (getattr(jrow, "latency_ms", None) is None):
                try:
                    jrow.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            pass
        db.close()


# ---------------- Benchmark ranking task ----------------
async def judge_ranking(
    ctx: dict[str, Any],
    job_id: str,
    candidates: dict[str, str],
    judge_provider: Optional[str],
    judge_model_id: Optional[str],
) -> str:
    """Rank multiple tailored resumes using one judge LLM.

    Inputs:
      - Job.resume_enc: base resume
      - Job.jd_enc: job description
      - candidates: mapping alias -> tailored resume text (provided by frontend)
    Behavior:
      - Stores a raw snapshot of candidates under JobOutput(type='tailored') for export parity
      - Stores the judge's formatted ranking narrative under JobOutput(type='judge')
      - Honors cancellation by checking Job.status before writes and between phases
    """
    from sqlalchemy.orm import Session
    from sqlalchemy import select, func, cast, Text as _Text, bindparam as _bind
    from restailor.db import SessionLocal, get_pii_key
    from restailor.models import Job, JobOutput
    from services.pricing import load_price_map
    from services.postprocess import record_charge_for_job

    db: Session = SessionLocal()
    start = time.perf_counter()
    try:
        # Path instrumentation: explicit judge_ranking entry
        try:
            logger.info({
                "evt": "judge_path",
                "path": "judge_ranking",
                "job_id": str(job_id),
                "candidate_count": len(candidates or {}),
            })
        except Exception:
            pass
        # Best-effort: clear any stale cancel flag
        try:
            r = ctx.get("redis") if isinstance(ctx, dict) else None
            if r is not None and hasattr(r, "get"):
                if await r.get(f"cancel:{job_id}"):
                    try:
                        await r.delete(f"cancel:{job_id}")
                    except Exception as e:
                        logger.debug("clear stale cancel flag (bench rank) failed: %r", e)
        except Exception as e:
            logger.debug("bench rank: cancel flag check failed: %r", e)
        try:
            pk = uuid.UUID(job_id)
        except Exception:
            pk = job_id  # type: ignore

        job = db.get(Job, pk)
        if job:
            job.status = "processing"
            try:
                # Collapse any legacy benchmark_rank / judgeN to 'judge'
                job.job_flow = "judge"
            except Exception:
                job.job_flow = "judge"
            try:
                db.commit()
            except Exception:
                db.rollback()

        # Candidate count computed lazily after reconstruction; define helper.
        def _cand_count() -> int:
            try:
                return max(1, len([v for v in (candidates or {}).values() if isinstance(v, str) and v.strip()]))
            except Exception:
                return 1

        # Decrypt base resume + JD
        pii_key = get_pii_key()
        row = db.execute(
            select(
                func.pgp_sym_decrypt(Job.resume_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("resume_text"),
                func.pgp_sym_decrypt(Job.jd_enc, cast(_bind("pg_key", value=pii_key), _Text)).label("jd_text"),
            ).where(Job.id == pk)
        ).first()
        if not row:
            try:
                logger.warning({
                    "evt": "worker_skip_missing_job",
                    "task": "judge_ranking",
                    "job_id": str(job_id),
                })
            except Exception:
                pass
            return "SKIP_MISSING_JOB"
        base_resume = row.resume_text or ""
        jd_text = row.jd_text or ""

        # Load candidates from encrypted DB storage if not provided (privacy: API avoided passing them via ARQ args)
        if not candidates:
            try:
                key_param = cast(_bind("pg_key", value=pii_key), _Text)
                cj = db.execute(
                    select(func.pgp_sym_decrypt(JobOutput.content_enc, key_param))
                    .where((JobOutput.job_id == pk) & (JobOutput.type == "bench_cands_json"))
                    .order_by(JobOutput.created_at.desc())
                    .limit(1)
                ).scalar()
                if cj:
                    import json as _json
                    parsed = _json.loads(cj)
                    if isinstance(parsed, dict):
                        candidates = {str(k): str(v or "") for k, v in parsed.items()}
            except Exception:
                candidates = candidates or {}
    # Intentionally do NOT reconstruct candidates from generic 'tailored' snapshot to avoid
    # misinterpreting single resumes (with section headings) as multiple candidates.
        # Candidate count now available via _cand_count()
        try:
            logger.info({"evt": "bench_cand_count", "job_id": str(job_id), "cand_count": _cand_count()})
        except Exception:
            pass
        # Non-PII diagnostics for observability
        try:
            _aliases = list(candidates.keys()) if isinstance(candidates, dict) else []
            logger.info({
                "evt": "bench_cands_loaded",
                "job_id": str(job_id),
                "alias_count": len(_aliases),
                "aliases": _aliases[:20],
            })
        except Exception as e:
            logger.debug("bench cands observability emit failed: %r", e)

    # Alias handling:
    # - If candidates are already alias-coded (e.g., persisted by API as R+hex), do NOT re-alias.
    # - Otherwise, apply deterministic HMAC aliasing as a fallback, using 6 hex to align with enqueue-side alias_map.
        try:
            import hmac as _hmac, hashlib as _hashlib, json as _json, re as _re
            if isinstance(candidates, dict):
                keys = list(candidates.keys())
                # Detect pre-aliased keys (R + 6..8 uppercase hex)
                _alias_pat = _re.compile(r"^R[0-9A-F]{6,8}$")
                _already_aliased = (len(keys) > 0 and all(isinstance(k, str) and _alias_pat.fullmatch(k or "") for k in keys))
                if not _already_aliased:
                    alias_secret = os.getenv("ALIAS_SECRET") or os.getenv("AUTH_SECRET_KEY")
                    if not alias_secret:
                        raise RuntimeError("alias_secret_missing: set ALIAS_SECRET or AUTH_SECRET_KEY for ranking")
                    alias_map: dict[str, str] = {}
                    new_candidates: dict[str, str] = {}
                    for orig_key, text in list(candidates.items()):
                        ok = str(orig_key)
                        msg = f"{job_id}:{ok}".encode("utf-8", errors="ignore")
                        digest = _hmac.new(alias_secret.encode("utf-8"), msg, _hashlib.sha256).hexdigest().upper()
                        alias = "R" + digest[:6]  # align with enqueue alias length
                        # Ensure uniqueness if pathological collision (extremely unlikely)
                        _i = 6
                        while alias in alias_map and alias_map.get(alias) != ok:
                            _i += 1
                            alias = "R" + _hmac.new(alias_secret.encode("utf-8"), f"{job_id}:{ok}:{_i}".encode("utf-8"), _hashlib.sha256).hexdigest().upper()[:max(6,_i)]
                        alias_map[alias] = ok
                        new_candidates[alias] = text
                    candidates = new_candidates
        except Exception as _alias_ex:
            logger.warning({"evt": "bench_rank_aliasing_failed", "job_id": str(job_id), "err": str(_alias_ex)})

        # Load judge rubric and build a single self-contained payload
        from pathlib import Path
        from datetime import datetime
        def _load_judge_prompt() -> str:
            try:
                root = Path(__file__).resolve().parent
                text = (root / "prompts" / "judge.md").read_text(encoding="utf-8").strip()
            except Exception:
                return "Rank from best to worst. Provide Overall, JD Fit, and Honesty scores, then a brief analysis and a final order."
            try:
                now = datetime.now()
                iso = now.strftime("%Y-%m-%d")
                human = now.strftime("%B %d, %Y")
                year = now.strftime("%Y")
                return (
                    text.replace("[[TODAY_ISO]]", iso)
                        .replace("[[TODAY]]", human)
                        .replace("[[CURRENT_YEAR]]", year)
                )
            except Exception:
                return text

        def _build_payload() -> str:
            rubric = _load_judge_prompt()
            aliases = list(candidates.keys())
            alias_lines = "\n".join(f"- {a}" for a in aliases)
            n = len(aliases)
            header = (
                "=== RUBRIC ===\n" + rubric + "\n\n"
                + "=== BASE_RESUME ===\n" + (base_resume or "") + "\n\n"
                + "=== JOB_DESCRIPTION ===\n" + (jd_text or "") + "\n\n"
                + "=== INSTRUCTIONS_OVERRIDE ===\n"
                + f"There {'is' if n==1 else 'are'} exactly {n} candidate resume{'s' if n!=1 else ''}.\n"
                + "Aliases (in arbitrary order):\n" + alias_lines + "\n\n"
                + ("Use Mode 1: Single Resume Analysis.\n" if n == 1 else ("Use Mode 2: Head-to-Head Comparison.\n" if n == 2 else "Use Mode 3: Ranking Mode.\n"))
                + "Do not invent any additional resumes or aliases. Only evaluate aliases listed above.\n"
                + "If any alias is missing content, ignore it.\n\n"
                + "=== CANDIDATE RESUMES (alias ΓåÆ text) ===\n"
            )
            parts = [header]
            for alias, text in candidates.items():
                parts.append(f"[ALIAS] {alias}\n[text]\n{(text or '').strip()}\n\n")
            return "".join(parts)

        # Redis helpers and streaming judge using unified streaming layer
        # Redis from ctx for cancel checks and progress
        redis = ctx.get("redis") if isinstance(ctx, dict) else None
        if redis is None:
            class _Null:
                async def set(self, *a, **k): pass
                async def get(self, *a, **k): return None
                async def append(self, *a, **k): return 0
                async def expire(self, *a, **k): pass
                async def pipeline(self, *a, **k):
                    class P:
                        async def execute(self): return []
                        def append(self, *a, **k): return self
                        def set(self, *a, **k): return self
                    return P()
            redis = _Null()
        meta_key = f"job:{job_id}:meta"
        buf_key = f"job:{job_id}:buf"
        art_key = f"job:{job_id}:artifact"

        async def _set_meta(**fields: Any) -> None:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                data: dict[str, Any] = {}
                if cur:
                    try:
                        data = _json.loads(cur if isinstance(cur, str) else cur.decode("utf-8", errors="ignore"))
                    except Exception:
                        data = {}
                data.update(fields)
                await redis.set(meta_key, _json.dumps(data))  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_set_meta (bench rank) failed: %r", e)
        async def _append(chunk: str) -> int:
            try:
                new_len = await redis.append(buf_key, chunk)  # type: ignore[attr-defined]
                return int(new_len or 0)
            except Exception:
                try:
                    cur = await redis.get(buf_key)  # type: ignore[attr-defined]
                    s = (cur.decode("utf-8", errors="ignore") if isinstance(cur, (bytes, bytearray)) else (cur or ""))
                except Exception:
                    s = ""
                s2 = s + (chunk or "")
                try:
                    await redis.set(buf_key, s2)  # type: ignore[attr-defined]
                except Exception as e:
                    logger.debug("redis.set in _append (bench rank) failed: %r", e)
                return len(s2.encode("utf-8"))
        async def _expire_keys(ttl: int = 600) -> None:
            try:
                if hasattr(redis, "expire"):
                    await redis.expire(meta_key, ttl)  # type: ignore[attr-defined]
                    await redis.expire(buf_key, ttl)   # type: ignore[attr-defined]
                    await redis.expire(art_key, ttl)   # type: ignore[attr-defined]
            except Exception as e:
                logger.debug("_expire_keys (bench rank) failed: %r", e)
        async def _get_cancel() -> bool:
            try:
                v = await redis.get(f"cancel:{job_id}")  # type: ignore[attr-defined]
                return bool(v)
            except Exception:
                return False
        async def _read_meta() -> dict[str, Any]:
            import json as _json
            try:
                cur = await redis.get(meta_key)  # type: ignore[attr-defined]
                if not cur:
                    return {}
                if isinstance(cur, (bytes, bytearray)):
                    return _json.loads(cur.decode("utf-8", errors="ignore"))
                if isinstance(cur, str):
                    return _json.loads(cur)
                return {}
            except Exception:
                return {}

        # If canceled, stop before heavy work or right at the start
        if job:
            try:
                db.refresh(job)
            except Exception as e:
                logger.debug("db.refresh(job) pre-cancel check (bench rank) failed: %r", e)
            if getattr(job, "status", None) == "failed":
                return "CANCELED"
        try:
            if await _get_cancel():
                await _set_meta(state="cancelled", updated_at=time.time())
                if job:
                    try:
                        job.status = "failed"
                        try:
                            job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                        except Exception:
                            pass
                        db.commit()
                    except Exception:
                        db.rollback()
                return "CANCELED"
        except Exception as e:
            logger.debug("early cancel check (bench rank) failed: %r", e)

        # Guard: require at least two candidates for benchmarking; otherwise, skip
        try:
            cand_count = len([v for v in (candidates or {}).values() if isinstance(v, str) and v.strip()])
        except Exception:
            cand_count = 0
        if cand_count < 2:
            try:
                await _set_meta(
                    state="skipped",
                    updated_at=time.time(),
                    reason=("single_candidate" if cand_count == 1 else "no_candidates"),
                )
            except Exception:
                pass
            if job:
                try:
                    job.status = "completed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            return ("SKIP:SINGLE_CANDIDATE" if cand_count == 1 else "SKIP:NO_CANDIDATES")

        # Raw snapshot of candidates may already be saved by API. If not, save best-effort.
        try:
            key = get_pii_key()
            key_param = cast(_bind("pg_key", value=key), _Text)
            existing = db.execute(
                select(func.count())
                .select_from(JobOutput)
                .where((JobOutput.job_id == pk) & (JobOutput.type == "tailored"))
            ).scalar() or 0
            if existing == 0 and candidates:
                raw_md = []
                for alias, text in candidates.items():
                    raw_md.append(f"### {alias}\n\n{(text or '').strip()}\n")
                raw_blob = "\n".join(raw_md)
                out_raw = JobOutput(job_id=pk, type="tailored")
                db.add(out_raw); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value=raw_blob, type_=sa.Text),
                        sa.bindparam("k", value=key, type_=sa.Text),
                        sa.bindparam("id", value=str(out_raw.id)),
                    )
                )
                db.commit()
        except Exception:
            db.rollback()

        # Streaming judge via unified streaming layer
        from restailor.app_config import CONFIG as _CFG
        from services.llm import stream_model, abort_job, StallBeforeFirstByte
        from config_loader import build_gen_params

        # Build system and user prompts
        sys_prompt = _load_judge_prompt()
        user_full = _build_payload() + "\n\n<<END>>"
        # Token helpers and prompt estimate (use shared helper)
        _tokens_in = _chars_to_tokens(len(sys_prompt or "") + len(user_full or ""))

        # Init meta & coalescing
        t_start = time.time()
        t_first_chunk = None
        await _set_meta(
            state="running",
            bytes=0,
            updated_at=t_start,
            t_start=t_start,
            rt_ignore_cancel=_get_env_bool("RT_IGNORE_CANCEL", False),
            tokens_in=int(_tokens_in),
            tokens_out_streamed=0,
        )

        # Build generation params & timeouts
        try:
            params = build_gen_params(_CFG, (judge_provider or ""), "judge", (judge_model_id or ""))  # type: ignore[arg-type]
        except Exception:
            params = {}
        try:
            timeouts = _merge_timeouts(_CFG, (judge_provider or ""), (judge_model_id or ""))  # per-model override restore
        except Exception:
            timeouts = {}
        _ignore_cancel = _get_env_bool("RT_IGNORE_CANCEL", False)

        # Coalescing and external cancel helpers (shared)
        RT_COALESCE_MS = max(COALESCE_MS_MIN, min(COALESCE_MS_MAX, _get_env_int("RT_COALESCE_MS", COALESCE_MS_DEFAULT)))
        RT_COALESCE_BYTES = max(COALESCE_BYTES_MIN, min(COALESCE_BYTES_MAX, _get_env_int("RT_COALESCE_BYTES", COALESCE_BYTES_DEFAULT)))
        coalescer = Coalescer(
            redis=redis,
            meta_key=meta_key,
            buf_key=buf_key,
            t_start=t_start,
            tokens_in=int(_tokens_in),
            rt_coalesce_ms=RT_COALESCE_MS,
            rt_coalesce_bytes=RT_COALESCE_BYTES,
        )
        external_cancel = _make_external_cancel(redis, job_id, _ignore_cancel)

        # Streaming judge ranking using unified streaming layer
        try:
            async for chunk in stream_model(
                provider=(judge_provider or ''),
                model=(judge_model_id or ''),
                system_prompt=sys_prompt,
                user_prompt=user_full,
                params=params,
                timeouts=timeouts,
                # Ranking uses a fixed marker literal in payload; add it here for clipping.
                stop_markers=["<<END>>"],
                job_id=job_id,
                external_cancel=(None if _ignore_cancel else external_cancel),
            ):
                if (not _ignore_cancel) and await external_cancel():
                    try:
                        abort_job(job_id)
                    except Exception as e:
                        logger.debug("abort_job during bench rank cancel failed: %r", e)
                    await coalescer.flush(force=True)
                    await _set_meta(state="cancelled", updated_at=time.time())
                    await _expire_keys()
                    if job:
                        try:
                            job.status = "failed"; db.commit()
                        except Exception:
                            db.rollback()
                    try:
                        pm = load_price_map()
                        m = await _read_meta()
                        prompt_tokens = int(m.get("tokens_in", 0) or 0)
                        completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                        if job is not None and getattr(job, "user_id", None):
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                                provider=str(judge_provider or ""),
                                model=str(judge_model_id or ""),
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                price_map=pm,
                                pricing_version=int(pm.get("version", 1)),
                                prompt_tokens_real=None,
                                completion_tokens_real=None,
                                token_estimation_method="heuristic_chars_div4",
                                output_models=_cand_count(),
                                input_models=0,
                            )
                            db.commit()
                    except Exception:
                        db.rollback()
                    return "CANCELED"
                if t_first_chunk is None:
                    t_first_chunk = time.time(); await _set_meta(t_first_chunk=t_first_chunk)
                c = (chunk or "")
                if c:
                    await coalescer.append(c)
                await coalescer.flush(force=(coalescer.total == 0))
                await asyncio.sleep(0)
        except StallBeforeFirstByte:
            await _set_meta(state="failed", updated_at=time.time()); await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                        provider=str(judge_provider or ""),
                        model=str(judge_model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=None,
                        completion_tokens_real=None,
                        token_estimation_method="heuristic_chars_div4",
                        output_models=_cand_count(),
                        input_models=0,
                    )
                    db.commit()
            except Exception:
                db.rollback()
            return "FAILED:STALL_BEFORE_FIRST"
        except asyncio.CancelledError:
            try:
                abort_job(job_id)
            except Exception as e:
                logger.debug("abort_job on CancelledError failed: %r", e)
            await _set_meta(state="cancelled", updated_at=time.time()); await _expire_keys()
            if job:
                try:
                    job.status = "failed"
                    try:
                        job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    except Exception:
                        pass
                    db.commit()
                except Exception:
                    db.rollback()
            try:
                pm = load_price_map()
                m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                        provider=str(judge_provider or ""),
                        model=str(judge_model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=None,
                        completion_tokens_real=None,
                        token_estimation_method="heuristic_chars_div4",
                        output_models=_cand_count(),
                        input_models=0,
                    )
                    db.commit()
            except Exception:
                db.rollback()
            return "CANCELED"

        # Finalize: persist judge narrative and mark job completed
        try:
            await coalescer.flush(force=True)
        except Exception as e:
            logger.debug("final flush (section) failed: %r", e)
        final_text = ""
        try:
            buf = await redis.get(buf_key)  # type: ignore[attr-defined]
            if buf:
                final_text = buf.decode("utf-8", errors="ignore") if isinstance(buf, (bytes, bytearray)) else str(buf)
        except Exception as e:
            logger.debug("read final buffer (section) failed: %r", e)
        try:
            await redis.set(art_key, final_text)  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("set final artifact (section) failed: %r", e)
        if job:
            # Respect privacy preference: skip persisting judge narrative if opted-out.
            try:
                from restailor.privacy import should_persist_user_content
                from restailor.models import User as _U
                u = db.get(_U, getattr(job, "user_id", None)) if getattr(job, "user_id", None) else None
                persist_ok = bool(u and should_persist_user_content(u))
            except Exception:
                persist_ok = True
            if persist_ok:
                # Reverse alias substitution: replace alias codes back to original model names for persisted narrative.
                # Visibility is controlled by config/testing.show_judge_alias_codes (default false):
                #   - false: hide alias codes and do NOT append the legend
                #   - true:  show alias codes inline and append the alias legend
                try:
                    # Load alias_map if present
                    key_alias = get_pii_key()
                    alias_json = db.execute(
                        sa.text("SELECT pgp_sym_decrypt(content_enc, CAST(:k AS TEXT)) FROM job_outputs WHERE job_id = :j AND type='alias_map' ORDER BY created_at DESC LIMIT 1")
                        .bindparams(sa.bindparam("k", value=key_alias, type_=sa.Text), sa.bindparam("j", value=str(pk), type_=sa.Text))
                    ).scalar()
                    if alias_json and isinstance(alias_json, str) and alias_json.strip():
                        import json as _json, re as _re
                        amap = _json.loads(alias_json)
                        if isinstance(amap, dict) and len(amap) >= 1:
                            # amap maps alias->original (or original?), earlier code stored alias_map as alias->original_key
                            # We want to replace occurrences of alias codes with original names.
                            # Longer aliases first to avoid partial collisions.
                            # Determine visibility from app config
                            try:
                                _cfg_testing = (CONFIG.get("testing") or {}) if isinstance(CONFIG.get("testing"), dict) else {}
                            except Exception:
                                _cfg_testing = {}
                            _include_alias_codes = bool(_cfg_testing.get("show_judge_alias_codes", False))
                            for alias_code in sorted(amap.keys(), key=len, reverse=True):
                                orig_name = str(amap[alias_code])
                                if not alias_code or not orig_name:
                                    continue
                                # Boundary-aware substitution: avoid partial replacements within longer tokens
                                _pat = _re.compile(rf"(?<![A-Za-z0-9]){_re.escape(alias_code)}(?![A-Za-z0-9])")
                                replacement = f"{orig_name} [alias: {alias_code}]" if _include_alias_codes else orig_name
                                final_text = _pat.sub(replacement, final_text)
                            if _include_alias_codes:
                                try:
                                    # Append legend only when codes are shown
                                    legend_lines = ["\n\n---\nAlias Legend:\n"]
                                    for alias_code in sorted(amap.keys()):
                                        orig_name = str(amap[alias_code])
                                        legend_lines.append(f"- {alias_code} -> {orig_name}")
                                    final_text += "\n" + "\n".join(legend_lines)
                                except Exception:
                                    pass
                except Exception as _rev_ex:  # pragma: no cover
                    logger.debug("alias reverse substitution failed: %r", _rev_ex)
                key2 = get_pii_key()
                out_j = JobOutput(job_id=pk, type="judge")
                db.add(out_j); db.flush()
                db.execute(
                    sa.text("UPDATE job_outputs SET content_enc = pgp_sym_encrypt(:v, CAST(:k AS TEXT)) WHERE id = :id")
                    .bindparams(
                        sa.bindparam("v", value=(final_text or ""), type_=sa.Text),
                        sa.bindparam("k", value=key2, type_=sa.Text),
                        sa.bindparam("id", value=str(out_j.id)),
                    )
                )
            try:
                job.status = "completed"
                try:
                    job.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                except Exception:
                    pass
                db.commit()
            except Exception:
                db.rollback()
            # Record final charge (idempotent per job) with guard & recovery
            try:
                pm = load_price_map(); m = await _read_meta()
                prompt_tokens = int(m.get("tokens_in", 0) or 0)
                completion_tokens = int(m.get("tokens_out_streamed", 0) or 0)
                if job is not None and getattr(job, "user_id", None):
                    record_charge_for_job(
                        db,
                        user_id=int(getattr(job, "user_id", 0) or 0),
                        job_id=pk,
                        request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                        provider=str(judge_provider or ""),
                        model=str(judge_model_id or ""),
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        price_map=pm,
                        pricing_version=int(pm.get("version", 1)),
                        prompt_tokens_real=None,
                        completion_tokens_real=None,
                        token_estimation_method="heuristic_chars_div4",
                        output_models=_cand_count(),
                        input_models=0,
                    ); db.commit()
            except Exception as e:
                logger.warning("charge.final_attempt_failed job=%s flow=judge err_type=%s err_msg=%s", pk, type(e).__name__, str(e)[:200]); db.rollback()
            # Guard recovery
            try:
                if job is not None and getattr(job, "user_id", None):
                    from restailor.models import Charge as _Charge
                    exists = db.query(_Charge.id).filter(_Charge.job_id == pk).first() is not None
                    if not exists:
                        logger.warning("charge.guard_missing_detected job=%s flow=judge attempting_recovery=1", pk)
                        try: pm2 = load_price_map()
                        except Exception as e2:
                            logger.warning("charge.guard_load_price_map_failed job=%s flow=judge err=%r", pk, e2); pm2 = {"multiplier":1, "currency":"USD", "version":1, "models":{}}
                        try: m2 = await _read_meta()
                        except Exception: m2 = {}
                        pt2 = int((m2.get("tokens_in", 0) or 0)); ct2 = int((m2.get("tokens_out_streamed", 0) or 0))
                        try:
                            record_charge_for_job(
                                db,
                                user_id=int(getattr(job, "user_id", 0) or 0),
                                job_id=pk,
                                request_type=str(getattr(job, "job_flow", "judge") or "judge"),
                                provider=str(judge_provider or ""),
                                model=str(judge_model_id or ""),
                                prompt_tokens=pt2,
                                completion_tokens=ct2,
                                price_map=pm2,
                                pricing_version=int(pm2.get("version", 1) if isinstance(pm2, dict) else 1),
                                prompt_tokens_real=None,
                                completion_tokens_real=None,
                                token_estimation_method="guard_recovery",
                                output_models=_cand_count(),
                                input_models=0,
                            ); db.commit()
                            exists2 = db.query(_Charge.id).filter(_Charge.job_id == pk).first() is not None
                            if exists2: logger.warning("charge.guard_recovery_success job=%s flow=judge", pk)
                            else: logger.error("charge.guard_recovery_failed_no_row job=%s flow=judge", pk)
                        except Exception as e3:
                            db.rollback(); logger.error("charge.guard_recovery_exception job=%s flow=judge err_type=%s err_msg=%s", pk, type(e3).__name__, str(e3)[:200])
            except Exception as e_guard:
                logger.error("charge.guard_outer_exception job=%s flow=judge err_type=%s err_msg=%s", pk, type(e_guard).__name__, str(e_guard)[:200])
        await _set_meta(state="succeeded", updated_at=time.time(), artifact_key=art_key)
        return "OK"
    except Exception:
        # Avoid referencing possibly unbound local; fetch job row directly for failure marking.
        try:
            try:
                pk_fail = uuid.UUID(job_id)
            except Exception:
                pk_fail = job_id  # type: ignore[assignment]
            job_row = db.get(Job, pk_fail)
            if job_row is not None:
                job_row.status = "failed"
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        raise
    finally:
        # Fallback: ensure latency is set if still NULL
        try:
            try:
                _pk = uuid.UUID(job_id)
            except Exception:
                _pk = job_id  # type: ignore
            from restailor.models import Job as _Job
            jrow = db.get(_Job, _pk)
            if jrow is not None and (getattr(jrow, "latency_ms", None) is None):
                try:
                    jrow.latency_ms = int((time.perf_counter() - start) * MILLISECONDS_PER_SECOND)
                    db.commit()
                except Exception:
                    db.rollback()
        except Exception:
            pass
        db.close()


# --- Analytics snapshot rebuild --------------------------------------------
async def rebuild_user_analytics(ctx: dict[str, Any], user_id: int) -> str:
    from sqlalchemy.orm import Session
    from restailor.db import SessionLocal

    db: Session = SessionLocal()
    try:
        rebuild_snapshot_state(db, int(user_id))
        return "OK"
    except Exception as ex:
        try:
            db.rollback()
        except Exception:
            pass
        logger.debug("analytics.rebuild failed: %r", ex, exc_info=True)
        raise
    finally:
        db.close()


# --- Synthetic abort sanity job -------------------------------------------------
async def _abort_sanity_job(ctx: dict[str, Any], seconds: int = 10) -> str:
    """Sleep for N seconds but support ARQ cancellation via Job.abort().

    Acceptance: starting with 10s then calling Job.abort() interrupts within ~1s.
    Logs must show start and cancelled lines.
    """
    import asyncio, logging
    logging.info("abort_sanity: start")
    try:
        await asyncio.sleep(seconds)
        return "done"
    except asyncio.CancelledError:
        logging.info("abort_sanity: cancelled")
        raise


# --- Worker lifecycle hooks ---------------------------------------------------
async def _worker_on_startup(ctx: dict[str, Any]) -> None:
    try:
        logger.info({"evt": "arq_startup"})
    except Exception:
        pass


async def _worker_on_shutdown(ctx: dict[str, Any]) -> None:
    # Best-effort: close ARQ-provided redis connection cleanly
    try:
        r = ctx.get("redis")
        if r is not None:
            if hasattr(r, "aclose"):
                await r.aclose()  # type: ignore[attr-defined]
            elif hasattr(r, "close"):
                _res = r.close()  # type: ignore[attr-defined]
                import asyncio as _asyncio
                if _asyncio.iscoroutine(_res):  # type: ignore[arg-type]
                    await _res  # type: ignore[misc]
    except Exception as e:
        logger.debug("arq shutdown: redis close failed: %r", e)
    try:
        logger.info({"evt": "arq_shutdown"})
    except Exception:
        pass


# Re-declare WorkerSettings after all task functions are defined
class WorkerSettings:
    # Register tasks here
    functions = [
        tailor_resume,
        check_job_fit,
        judge_only,
        judge_ranking,
        rebuild_user_analytics,
        _abort_sanity_job,
    # Destructive tasks
    # delete_all_user_data and delete_account defined below
    ]

    # Point to local Redis (matches docker-compose defaults) with REDIS_URL override
    url = os.getenv("REDIS_URL") or os.getenv("RATE_LIMIT_STORAGE_URI")
    if url and isinstance(url, str) and url.strip():
        try:
            from urllib.parse import urlparse
            u = urlparse(url)
            _host = u.hostname or "127.0.0.1"
            try:
                _port = int(u.port or 6379)
            except Exception:
                _port = 6379
            try:
                _db = int((u.path or "/0").lstrip("/") or "0")
            except Exception:
                _db = 0
            _pw = u.password or None
            redis_settings = RedisSettings(host=_host, port=_port, database=_db, password=_pw)
        except Exception:
            redis_settings = None  # type: ignore
    else:
        # Build Redis settings from CONFIG/env
        try:
            rconf = (CONFIG.get("redis", {}) or {})
        except Exception:
            rconf = {}
        host = str(os.getenv("REDIS_HOST") or rconf.get("host") or "127.0.0.1")
        try:
            port = int(os.getenv("REDIS_PORT") or rconf.get("port") or 6379)
        except Exception:
            port = 6379
        try:
            database = int(os.getenv("REDIS_DB") or rconf.get("database") or 0)
        except Exception:
            database = 0
        password = os.getenv("REDIS_PASSWORD") or rconf.get("password") or None
        redis_settings = RedisSettings(host=host, port=port, database=database, password=password)

    # Optional: queue name, concurrency, cron, etc.
    # job_serializer = None
    # burst = False
    # Dynamic max_jobs based on ARQ_MAX_JOBS env (default 10 if not set)
    max_jobs = int(os.getenv("ARQ_MAX_JOBS", "10"))

    # Allow ARQ to cancel running jobs via Job.abort() (can be disabled for diagnostics)
    import os as _os
    allow_abort_jobs = not bool(((_os.getenv("RT_DISABLE_ARQ_ABORT") or "").strip().lower()) in ("1","true","yes"))

    # Schedule periodic maintenance (placeholder, set after function is defined)
    cron_jobs: list = []
    # Graceful lifecycle
    on_startup = _worker_on_startup
    on_shutdown = _worker_on_shutdown


# --- Destructive user tasks ---------------------------------------------------
async def delete_all_user_data(ctx: dict[str, Any], user_id: int) -> str:
    """Hard-delete all content owned by a user, but not the User row.

    Idempotent: deletion is via DELETE ... WHERE so reruns are safe.
    Avoid logging any PII.
    """
    from sqlalchemy.orm import Session
    from restailor.db import SessionLocal
    from restailor.models import User, Job, JobOutput
    from restailor import twofa_repo
    from restailor.runs import get_run_jobs

    db: Session = SessionLocal()
    try:
        # Find jobs owned by user
        job_ids = [row[0] for row in db.execute(sa.select(Job.id).where(Job.user_id == int(user_id))).all()]
        # Delete job_outputs for those jobs
        if job_ids:
            db.execute(sa.delete(JobOutput).where(JobOutput.job_id.in_(job_ids)))
        # Delete jobs
        db.execute(sa.delete(Job).where(Job.user_id == int(user_id)))
        # Clear 2FA artifacts and last saved inputs on User (PII convenience fields)
        try:
            twofa_repo.purge_user_twofa_artifacts(db, int(user_id))
        except Exception as e:
            logger.debug("purge_user_twofa_artifacts failed: %r", e)
        # Clear current snapshot tracking on User
        try:
            db.execute(
                sa.update(User)
                .where(User.id == int(user_id))
                .values(current_snapshot_key=None)
            )
        except Exception as e:
            logger.debug("clear current snapshot tracking failed: %r", e)
        db.commit()

        # Best-effort: remove Redis caches/keys for this user
        r = ctx.get("redis")
        if r is not None:
            try:
                # Namespaced patterns we may use; guard against wildcards
                patterns = [
                    f"user:{int(user_id)}:*",
                    f"u:{int(user_id)}:*",
                ]
                for pat in patterns:
                    try:
                        async for k in r.iscan(match=pat):  # type: ignore[attr-defined]
                            try:
                                await r.delete(k)  # type: ignore[attr-defined]
                            except Exception as e:
                                logger.debug("redis delete key failed: %r", e)
                    except Exception as e:
                        # Fallback if iscan not available
                        try:
                            keys = await r.keys(pat)  # type: ignore[attr-defined]
                            if keys:
                                await r.delete(*keys)  # type: ignore[attr-defined]
                        except Exception as e:
                            logger.debug("redis keys/delete fallback failed: %r", e)
            except Exception as e:
                logger.debug("redis cleanup for user failed: %r", e)
        return "OK"
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def delete_account(ctx: dict[str, Any], user_id: int) -> str:
    """Mark a user account as deleted after clearing data.

    Sets deleted_at, zeros credits if present, and sets credits_forfeited_at.
    Idempotent: reruns will simply update the same fields.
    """
    from sqlalchemy.orm import Session
    from restailor.db import SessionLocal
    from restailor.models import User
    from datetime import datetime, timezone

    # Step 1: clear all user-owned data
    try:
        await delete_all_user_data(ctx, int(user_id))
    except Exception as e:
        # Continue to mark account even if data deletion partially failed
        logger.debug("delete_all_user_data raised, continuing: %r", e)

    db: Session = SessionLocal()
    try:
        u = db.get(User, int(user_id))
        if u is None:
            return "NOOP"
        now = datetime.now(timezone.utc)
        try:
            setattr(u, "deleted_at", now)
        except Exception as e:
            logger.debug("set deleted_at failed: %r", e)
        # Zero credits if field exists
        try:
            if hasattr(u, "credits"):
                setattr(u, "credits", 0)
        except Exception as e:
            logger.debug("zero credits failed: %r", e)
        # Set forfeited timestamp if field exists
        try:
            setattr(u, "credits_forfeited_at", now)
        except Exception as e:
            logger.debug("set credits_forfeited_at failed: %r", e)

        db.add(u)
        db.commit()

        # TODO: revoke sessions/JWTs if a token blacklist/store exists
        # Best-effort Redis cleanup of user sessions if any convention is used
        r = ctx.get("redis")
        if r is not None:
            try:
                for pat in (f"auth:{int(user_id)}:*", f"session:{int(user_id)}:*"):
                    try:
                        async for k in r.iscan(match=pat):  # type: ignore[attr-defined]
                            try:
                                await r.delete(k)  # type: ignore[attr-defined]
                            except Exception as e:
                                logger.debug("redis session delete failed: %r", e)
                    except Exception as e:
                        try:
                            keys = await r.keys(pat)  # type: ignore[attr-defined]
                            if keys:
                                await r.delete(*keys)  # type: ignore[attr-defined]
                        except Exception as e:
                            logger.debug("redis session keys/delete fallback failed: %r", e)
            except Exception as e:
                logger.debug("redis session cleanup failed: %r", e)
        return "OK"
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Re-register WorkerSettings with new functions
WorkerSettings.functions.extend([delete_all_user_data, delete_account])


# --- Maintenance tasks -------------------------------------------------------
async def cleanup_expired_twofa(ctx: dict[str, Any]) -> str:
    """Delete expired email OTPs and trusted devices. Runs safely any time."""
    from sqlalchemy.orm import Session
    from restailor.db import SessionLocal
    from restailor import twofa_repo

    db: Session = SessionLocal()
    try:
        n1 = twofa_repo.delete_expired_email_otps(db)
        n2 = twofa_repo.delete_expired_trusted_devices(db)
        # Also delete stale trusted devices that were never used after N days (e.g., 14)
        try:
            n3 = twofa_repo.delete_stale_unused_trusted_devices(db, older_than_days=int(os.getenv("TD_STALE_DAYS", "14")))
        except Exception:
            n3 = 0
        try:
            logger.info({"evt": "cleanup_2fa", "email_otps": int(n1), "trusted_devices": int(n2), "trusted_devices_stale": int(n3)})
        except Exception as e:
            logger.debug("cleanup_2fa logging failed: %r", e)
        return f"OK:{n1}/{n2}/{n3}"
    finally:
        db.close()


# Add maintenance task
WorkerSettings.functions.extend([cleanup_expired_twofa])
WorkerSettings.cron_jobs = [cron(cleanup_expired_twofa, hour={3}, minute={15})]
