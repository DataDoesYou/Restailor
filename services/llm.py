from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator, Dict, Optional, List, Callable, Awaitable
import inspect

from config_loader import load_config, get_testing
from perf.observability import outbound_timed  # PERF: outbound timing wrapper
import logging as _log
_LOG = _log.getLogger(__name__)

# Abort handle registry keyed by job_id (stores lightweight cancel functions)
_ABORTS: dict[str, Callable[[], None]] = {}
# Captured provider usage (prompt, completion) per job for post-stream billing
_USAGE_REAL: dict[str, tuple[int | None, int | None]] = {}

def get_usage_for_job(job_id: str) -> tuple[int | None, int | None]:
    # Try in-memory first
    usage = _USAGE_REAL.get(str(job_id))
    if usage is not None:
        return usage
    # Fallback: attempt Redis read (best-effort)
    try:
        import os, json
        from redis.asyncio import from_url as _redis_from_url  # type: ignore
        redis_url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        async def _fetch() -> tuple[int | None, int | None]:
            try:
                r = await _redis_from_url(redis_url, decode_responses=True)
                raw = await r.get(f"usage:{job_id}")
                if raw:
                    data = json.loads(raw)
                    p = data.get("p")
                    c = data.get("c")
                    # Coerce to ints defensively
                    try: p_i = int(p) if p is not None else None
                    except Exception: p_i = None
                    try: c_i = int(c) if c is not None else None
                    except Exception: c_i = None
                    _USAGE_REAL[str(job_id)] = (p_i, c_i)
                    try:
                        _LOG.warning({"evt": "usage_fetch_redis", "job_id": job_id})
                    except Exception:
                        pass
                    await r.close()
                    return (p_i, c_i)
                await r.close()
            except Exception as ex:  # pragma: no cover - best effort
                try:
                    _LOG.debug({"evt": "usage_fetch_redis_fail", "job_id": job_id, "err": str(ex)})
                except Exception:
                    pass
            return (None, None)
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Execute fetch coroutine within existing loop via ensure_future + result
            fut = asyncio.ensure_future(_fetch())
            # NOTE: we cannot run_until_complete on a running loop from sync context; return default later if pending
            # Best-effort: if future already done (unlikely) return it else fall through to async run outside
            if fut.done():
                return fut.result()
            else:
                # Fall back to spawning a new loop (safe small op)
                pass
        else:
            # Create a temporary loop just for fetch
            return asyncio.run(_fetch())
    except Exception:
        return (None, None)
    # Fallback default if earlier branches did not return (e.g., future pending in running loop)
    return (None, None)

def _store_usage(job_id: str, prompt: int | None, completion: int | None) -> None:
    try:
        _USAGE_REAL[str(job_id)] = (prompt, completion)
        try:
            _LOG.warning({"evt": "usage_store", "job_id": job_id, "prompt_tokens_real": prompt, "completion_tokens_real": completion})
        except Exception:
            pass
        # Fire-and-forget Redis persistence
        import os, json
        from redis.asyncio import from_url as _redis_from_url  # type: ignore
        redis_url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        async def _persist() -> None:
            try:
                r = await _redis_from_url(redis_url, decode_responses=True)
                await r.set(f"usage:{job_id}", json.dumps({"p": prompt, "c": completion}), ex=300)
                try:
                    _LOG.warning({"evt": "usage_store_redis", "job_id": job_id})
                except Exception:
                    pass
                await r.close()
            except Exception as ex:  # pragma: no cover - best effort
                try:
                    _LOG.debug({"evt": "usage_store_redis_fail", "job_id": job_id, "err": str(ex)})
                except Exception:
                    pass
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_persist())
        except RuntimeError:
            # No running loop; skip async persist (worker path may not need it)
            pass
    except Exception:
        pass

# Internal tunables (magic numbers -> named constants)
# - Async queue backpressure for SDK->async bridge
QUEUE_MAXSIZE: int = 100
# - For snapshot delta reconstruction in Gemini stream handler
SNAPSHOT_MAX_CHECK: int = 2000
# - Sleep between queue polls under backpressure
BACKPRESSURE_SLEEP_S: float = 0.05
# - Idle sleep while waiting for first byte/next token in spooler
IDLE_SLEEP_S: float = 0.1


def register_abort(job_id: str, cancel_fn: Callable[[], None]) -> None:
    """Register a cancel function for a given job_id.

    Subsequent calls will overwrite the previous one (last-writer wins).
    """
    if not job_id:
        return
    _ABORTS[job_id] = cancel_fn
    try:
        _LOG.info({"evt": "abort_register", "job_id": job_id})
    except Exception as ex:
        _LOG.debug("abort_register warn failed: %s", ex)


def abort_job(job_id: str) -> bool:
    """Abort a running job by invoking and removing its cancel function.

    Returns True if a cancel function was present and invoked, else False.
    """
    fn = _ABORTS.pop(job_id, None)
    if fn:
        # Capture a brief callsite stack for diagnostics (who invoked abort_job)
        callers: list[str] = []
        try:
            import inspect, os
            for fr in inspect.stack()[1:5]:
                try:
                    callers.append(f"{os.path.basename(fr.filename)}:{fr.lineno}:{fr.function}")
                except Exception as _e:
                    try:
                        _LOG.debug("gemini event handling error: %s", _e)
                    except Exception as _inner_ex:
                        _LOG.debug("abort_job: inner debug log failed: %s", _inner_ex)
                    break
        except Exception as _ex:
            callers = []
        try:
            _LOG.info({"evt": "abort_invoke", "job_id": job_id, "callers": callers})
        except Exception as ex:
            _LOG.debug("abort_invoke warn failed: %s", ex)
        try:
            fn()
        except Exception as ex:
            # Best-effort cancellation: ignore errors from provider SDKs
            import logging as _log
            _log.getLogger(__name__).debug("abort_job: cancel function raised: %s", ex)
        return True
    else:
        try:
            _LOG.info({"evt": "abort_invoke", "job_id": job_id, "callers": [], "missing": True})
        except Exception as ex:
            _LOG.debug("abort_invoke missing warn failed: %s", ex)
    return False


class StallBeforeFirstByte(Exception):
    pass


async def stream_model(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    params: Dict[str, Any],
    timeouts: Dict[str, Any],
    stop_markers: List[str] | None,
    job_id: str,
    external_cancel: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncIterator[str]:
    """Unified streaming generator across providers.

    - Uses provider streaming APIs where available (OpenAI, Anthropic, xAI).
    - Stores an abort handle keyed by job_id (best-effort; may be provider stream object).
    - Timeouts:
        * No first byte by first_byte_ms -> raise StallBeforeFirstByte (map to HTTP 504).
        * Stall after first byte exceeding stall_ms -> raise asyncio.TimeoutError('stall_timeout').
    - Only the caller-supplied params (from build_gen_params) are passed through.
    - Stops on first stop marker occurrence.
    """
    prov = (provider or "").strip().lower()
    cfg = load_config() or {}

    # Mock mode short-circuit: simulate streaming without calling providers
    tcfg = get_testing(cfg)
    if (tcfg.get("mode") or "").lower() == "mock":
        cancelled = False

        def _cancel() -> None:
            nonlocal cancelled
            cancelled = True

        register_abort(job_id, _cancel)

        async def _mock_stream() -> AsyncIterator[str]:
            chunk = str(tcfg.get("chunk_text") or "")
            count = int(tcfg.get("chunk_count") or 0)
            delay = float(tcfg.get("emit_delay_s") or 0.0)
            # Ensure quick first token for diag timing tests
            for i in range(count):
                if cancelled:
                    break
                yield chunk
                # First emission is immediate; subsequent respect delay
                if delay and i < count - 1:
                    await asyncio.sleep(delay)

        async for c in _mock_stream():
            yield c
        return
    # Use only the provided timeouts (expected to come from app.toml via caller)
    try:
        first_byte_ms = int(timeouts["first_byte_ms"])  # required
    except Exception as e:
        raise ValueError("timeouts.first_byte_ms missing or invalid") from e

    stall_raw = (timeouts.get("stream_stall_abort_ms"))
    if stall_raw is None:
        stall_raw = timeouts.get("stall_ms")  # legacy key support if provided by caller
    if stall_raw is None:
        raise ValueError("timeouts.stream_stall_abort_ms (or stall_ms) missing")
    stall_ms = int(stall_raw)

    stops = [s for s in (stop_markers or []) if isinstance(s, str) and s]
    saw_first = False
    buffer_tail = ""
    cancel_event = asyncio.Event()

    def _cancel() -> None:
        # Flag local cancel; provider streams will observe this and stop.
        try:
            cancel_event.set()
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("stream_model: cancel flag set failed: %s", ex)

    # Resolve API key like the worker: keyring first, then environment
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

    api_key = _get_api_key(prov)
    if prov in ("openai", "anthropic", "gemini", "xai") and not api_key:
        raise RuntimeError(
            f"Missing API key for provider '{prov}'. Add it via keyring (service='restailor', username='{('OPENAI_API_KEY' if prov=='openai' else 'CLAUDE_API_KEY' if prov=='anthropic' else 'GEMINI_API_KEY' if prov=='gemini' else 'GROK_API_KEY')}') or set the environment variable."
        )

    async def _maybe_close(obj: Any) -> None:
        try:
            fn = getattr(obj, "aclose", None)
            if callable(fn):
                res = fn()
                if inspect.isawaitable(res):
                    await res
                return
            fn2 = getattr(obj, "close", None)
            if callable(fn2):
                res2 = fn2()
                if inspect.isawaitable(res2):
                    await res2
        except Exception as ex:
            _LOG.debug("_maybe_close error (final response): %s", ex)

    async def _openai_stream() -> AsyncIterator[str]:
        """OpenAI streaming via Responses API only (no Chat Completions, no fallback).

        - Uses AsyncOpenAI.responses.create(stream=True)
        - Maps system_prompt -> instructions, user_prompt -> input (simple string per docs)
        - Maps params: temperature (except GPT-5), stop, max_tokens -> max_output_tokens
        - Preserves abort via cancel_event and closes the stream on cancel
        References:
          - openai/openai-python README: Responses API + Streaming responses (async)
          - https://github.com/openai/openai-python
        """
        from openai import AsyncOpenAI  # type: ignore
        client = AsyncOpenAI(api_key=api_key)

        rparams: Dict[str, Any] = {}
        actual_model = model  # Default to the provided model
        if isinstance(params, dict):
            # Extract actual model if virtual model ID was used
            actual_model = params.pop("_actual_model", model)
            mdl = (model or "").lower()
            if ("temperature" in params) and not mdl.startswith("gpt-5"):
                rparams["temperature"] = params["temperature"]
            # Responses API does not accept 'stop' at top-level; enforce via client-side marker clamp only
            # if "stop" in params: skip
            if "max_tokens" in params:
                rparams["max_output_tokens"] = params["max_tokens"]
            # Pass-through provider-sanctioned extras from params (build_gen_params)
            # Note: 'verbosity' is NOT supported by AsyncResponses.create(), so skip it.
            for _k in ("reasoning", "max_output_tokens"):
                if _k in params and _k not in rparams:
                    rparams[_k] = params[_k]

        # Simple input per docs; keep instructions separate
        input_text = (user_prompt or "")
        try:
            # PERF: time the outbound call that creates the streaming response
            async with outbound_timed("llm", "openai.responses.create", model=actual_model):
                stream = await client.responses.create(
                    model=actual_model,
                    instructions=system_prompt or None,
                    input=input_text,
                    stream=True,
                    **rparams,
                )

            def _abort_openai_resp() -> None:
                _cancel()
                asyncio.create_task(_maybe_close(stream))

            register_abort(job_id, _abort_openai_resp)

            async for event in stream:  # SSE events from Responses API
                if cancel_event.is_set():
                    await _maybe_close(stream)  # Immediately close connection on cancel
                    break
                et = getattr(event, "type", None)
                # Text deltas per SDK examples; support variations defensively
                # GPT-5 can emit response.content.delta as well
                mdl = (model or "").lower()
                if (
                    (not mdl.startswith("gpt-5") and et in ("response.output_text.delta", "response.text.delta", "response.delta", "output_text.delta"))
                    or (mdl.startswith("gpt-5") and et in ("response.output_text.delta", "response.text.delta", "response.delta", "output_text.delta", "response.content.delta"))
                ):
                    text_part = getattr(event, "delta", None) or getattr(event, "text", None)
                    if text_part:
                        yield str(text_part)
                
                # Capture usage from final events (completed, incomplete, or failed)
                # Usage is in event.response.usage, not event.usage
                if et in ("response.completed", "response.incomplete", "response.failed"):
                    try:
                        response_obj = getattr(event, "response", None)
                        if response_obj:
                            usage = getattr(response_obj, "usage", None)
                            if usage and hasattr(usage, "__dict__"):
                                usage_dict = vars(usage)
                                p = usage_dict.get("input_tokens") or usage_dict.get("prompt_tokens")
                                c = usage_dict.get("output_tokens") or usage_dict.get("completion_tokens")
                                try:
                                    p_i = int(p) if p is not None else None
                                except Exception:
                                    p_i = None
                                try:
                                    c_i = int(c) if c is not None else None
                                except Exception:
                                    c_i = None
                                _store_usage(job_id, p_i, c_i)
                    except Exception as ex:
                        _LOG.debug("openai usage extraction from %s event failed: %s", et, ex)
        except asyncio.CancelledError:
            await _maybe_close(client)
            raise
        finally:
            await _maybe_close(client)
        if False:
            yield ""  # PERF: appease static analyzers without behavior change

        return

    async def _xai_stream() -> AsyncIterator[str]:
        from openai import AsyncOpenAI  # type: ignore
        client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        # Remove internal metadata that xAI doesn't support
        _p = dict(params)
        _meta_role = _p.pop("_meta_role", None)
        req = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
        }
        req.update(_p)
        async with outbound_timed("llm", "xai.chat.completions.create", model=model):  # PERF
            stream = await client.chat.completions.create(**req)
        def _abort_xai() -> None:
            _cancel()
            asyncio.create_task(_maybe_close(stream))
        register_abort(job_id, _abort_xai)
        try:
            async for chunk in stream:
                if cancel_event.is_set():
                    await _maybe_close(stream)  # Immediately close connection on cancel
                    break
                delta = getattr(chunk.choices[0].delta, "content", None) if getattr(chunk, "choices", None) else None
                if not delta:
                    continue
                yield delta
            # After stream completion attempt final response usage
            try:
                final_resp = await stream.get_final_response()  # type: ignore[attr-defined]
                usage = getattr(final_resp, "usage", None) or {}
                if isinstance(usage, dict):
                    p = usage.get("prompt_tokens") or usage.get("input_tokens")
                    c = usage.get("completion_tokens") or usage.get("output_tokens")
                    _store_usage(job_id, int(p) if p is not None else None, int(c) if c is not None else None)
            except Exception as ex:
                _LOG.debug("xai final usage fetch failed: %s", ex)
        except asyncio.CancelledError:
            await _maybe_close(stream)
            await _maybe_close(client)
            raise
        finally:
            await _maybe_close(stream)
            await _maybe_close(client)

    async def _anthropic_stream() -> AsyncIterator[str]:
        from anthropic import AsyncAnthropic  # type: ignore
        client = AsyncAnthropic(api_key=api_key)
        # Anthropic requires max_tokens; ensure a sensible default if not provided.
        _p = dict(params)
        _meta_role = _p.pop("_meta_role", None)  # Remove internal metadata
        _effort = _p.pop("_effort", None)  # Extract effort param (Opus 4.5 beta)
        _p.setdefault("max_tokens", 4096)
        
        # Check if this is an Opus 4.5 model (supports effort parameter)
        is_opus_45 = "opus-4-5" in (model or "").lower() or "opus-4.5" in (model or "").lower()
        
        # Extended thinking: if budget is configured, ensure max_tokens accommodates it
        thinking_config = _p.get("thinking")
        if thinking_config and isinstance(thinking_config, dict):
            budget = thinking_config.get("budget_tokens", 0)
            # max_tokens must be >= budget_tokens for thinking to work properly
            if budget and _p.get("max_tokens", 0) < budget:
                _p["max_tokens"] = budget + 4096  # Add headroom for text output
            # Extended thinking requires temperature=1 (API constraint)
            if "temperature" in _p:
                _p.pop("temperature")
        
        # Use beta endpoint for effort parameter (Opus 4.5 only)
        use_beta = is_opus_45 and _effort
        
        async with outbound_timed("llm", "anthropic.messages.create", model=model):  # PERF
            if use_beta:
                # Effort parameter requires beta endpoint with betas list
                stream = await client.beta.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    stream=True,
                    betas=["effort-2025-11-24"],
                    output_config={"effort": _effort},
                    **_p,
                )
            else:
                stream = await client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    stream=True,
                    **_p,
                )
        def _abort_anthropic() -> None:
            _cancel()
            asyncio.create_task(_maybe_close(stream))
        register_abort(job_id, _abort_anthropic)
        try:
            async for ev in stream:
                if cancel_event.is_set():
                    # Stop emitting further tokens immediately; the caller loop will observe cancel
                    await _maybe_close(stream)  # Immediately close connection on cancel
                    break
                t = getattr(ev, "type", None)
                if t == "content_block_delta":
                    delta = getattr(ev, "delta", None)
                    # Handle both text deltas and thinking deltas
                    delta_type = getattr(delta, "type", None) if delta else None
                    if delta_type == "text_delta":
                        text = getattr(delta, "text", "") if delta else ""
                        if text:
                            yield text
                    elif delta_type == "thinking_delta":
                        # Extended thinking: we receive summarized thinking but don't emit it
                        # The thinking is processed internally by Claude
                        pass
                    else:
                        # Fallback for older response format
                        text = getattr(delta, "text", "") if delta else ""
                        if text:
                            yield text
            # Final usage via get_final_response
            try:
                final_resp = await stream.get_final_response()  # type: ignore[attr-defined]
                usage = getattr(final_resp, "usage", None) or {}
                if isinstance(usage, dict):
                    p = usage.get("input_tokens")
                    c = usage.get("output_tokens")
                    _store_usage(job_id, int(p) if p is not None else None, int(c) if c is not None else None)
            except Exception as ex:
                _LOG.debug("anthropic final usage fetch failed: %s", ex)
        except asyncio.CancelledError:
            await _maybe_close(stream)
            await _maybe_close(client)
            raise
        finally:
            await _maybe_close(stream)
            await _maybe_close(client)

    async def _gemini_stream() -> AsyncIterator[str]:
        # Try SDK streaming; if unavailable, fall back to chunking the full text.
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore
        client = genai.Client(api_key=api_key)
        # Prefer plain-text responses; keep params merged from config (snake_case)
        # Coerce 'thinking' dict into SDK type to ensure it's honored
        _p = dict(params)
        # Extract role metadata (if provided by build_gen_params) before mutating _p
        _meta_role = _p.pop("_meta_role", None)
        # Map OpenAI-style "max_tokens" to Gemini's expected "max_output_tokens"
        try:
            if "max_output_tokens" not in _p and "max_tokens" in _p:
                mt_val = _p.pop("max_tokens")
                try:
                    _p["max_output_tokens"] = int(mt_val)  # normalize to int
                except Exception:
                    # If not coercible just drop; Gemini SDK will use its default
                    pass
            # If still no max_output_tokens, fall back to highest configured role output cap
            if "max_output_tokens" not in _p:
                try:
                    role_defaults = (cfg.get("limits", {}).get("role_outputs") or {})  # outer cfg from earlier load
                    if _meta_role and _meta_role in role_defaults:
                        _p["max_output_tokens"] = int(role_defaults[_meta_role])
                    else:
                        # choose largest to minimize premature truncation (tailor/fit=4096, judge=16384)
                        candidate = max((int(v) for v in role_defaults.values() if isinstance(v, (int, float))), default=4096)
                        _p["max_output_tokens"] = int(candidate)
                except Exception:
                    _p["max_output_tokens"] = 4096
        except Exception:
            pass
        try:
            th = _p.get("thinking")
            if isinstance(th, dict):
                try:
                    _p["thinking"] = types.ThinkingConfig(**th)
                except Exception:
                    # If SDK signature changes, drop thinking to avoid errors
                    _p.pop("thinking", None)
        except Exception:
            pass
    # Disable thinking ONLY for flash variants (pro keeps configured thinking budget)
        try:
            if "flash" in (model or "").lower():
                if _p.pop("thinking", None) is not None:
                    _LOG.warning({
                        "evt": "gemini_disable_thinking_flash",
                        "job_id": job_id,
                        "model": model,
                        "role": _meta_role,
                        "reason": "flash_variant"
                    })
        except Exception:
            pass
        try:
            # Build Gemini generation config (avoid shadowing outer app config variable by naming gen_cfg)
            gen_cfg = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="text/plain",
                **_p,
            )
        except Exception:
            gen_cfg = types.GenerateContentConfig(system_instruction=system_prompt, **_p)
        # Emit one structured diagnostic log with the resolved generation parameters (role-aware)
        try:
            thinking_cfg = _p.get("thinking")
            # thinking_cfg might be a dict or a ThinkingConfig object
            budget = None
            level = None
            inc_thoughts = None
            
            if isinstance(thinking_cfg, dict):
                budget = thinking_cfg.get("budget_tokens")
                level = thinking_cfg.get("thinking_level")
                inc_thoughts = thinking_cfg.get("include_thoughts")
            elif thinking_cfg is not None:
                # Assume it's a ThinkingConfig object
                budget = getattr(thinking_cfg, "budget_tokens", None)
                level = getattr(thinking_cfg, "thinking_level", None)
                inc_thoughts = getattr(thinking_cfg, "include_thoughts", None)

            _LOG.info({
                "evt": "gemini_effective_params",
                "job_id": job_id,
                "model": model,
                "role": _meta_role,
                "max_output_tokens": _p.get("max_output_tokens"),
                "thinking_budget_tokens": budget,
                "thinking_level": level,
                "include_thoughts": inc_thoughts,
            })
        except Exception as ex:
            _LOG.debug("gemini effective params log failed: %s", ex)
        # Cancellation flag is shared via cancel_event
        # Always adapt SDK streaming to async using a background thread + asyncio.Queue
        try:
            loop = asyncio.get_running_loop()
            q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
            stream_holder: dict[str, Any] = {"stream": None, "final_text": ""}
            _resolved_cap = _p.get("max_output_tokens")

            def _pump() -> None:
                warn70 = False
                warn95 = False
                finish_reasons: set[str] = set()
                try:
                    try:
                        s = client.models.generate_content_stream(
                            model=model,
                            contents=user_prompt,
                            config=gen_cfg,
                        )
                        stream_holder["stream"] = s
                    except Exception as e:
                        _LOG.error("gemini stream init failed: %s", e)
                        loop.call_soon_threadsafe(q.put_nowait, None)
                        return
                    accum = ""

                    def _emit_delta(piece: str) -> None:
                        if not piece:
                            return
                        try:
                            loop.call_soon_threadsafe(q.put_nowait, piece)
                        except Exception as ex:
                            _LOG.debug("gemini queue put failed: %s", ex)

                    for ev in stream_holder["stream"]:
                        if cancel_event.is_set():
                            break
                        try:
                            # Collect finish reasons if present on candidates
                            try:
                                cands_fr = getattr(ev, "candidates", None)
                                if cands_fr:
                                    for c in cands_fr:
                                        fr = getattr(c, "finish_reason", None) or getattr(c, "finishReason", None)
                                        if fr:
                                            finish_reasons.add(str(fr))
                            except Exception:
                                pass
                            t = getattr(ev, "text", None)
                            if isinstance(t, str) and t:
                                _emit_delta(t)
                                accum += t
                                stream_holder["final_text"] = accum
                            else:
                                snap = None
                                try:
                                    cands = getattr(ev, "candidates", None)
                                    if cands:
                                        for c in cands:
                                            content_obj = getattr(c, "content", None)
                                            parts = getattr(content_obj, "parts", None) if content_obj is not None else None
                                            if parts:
                                                s_acc: List[str] = []
                                                for p in parts:
                                                    ptext = getattr(p, "text", None)
                                                    if ptext:
                                                        s_acc.append(str(ptext))
                                                if s_acc:
                                                    snap = "".join(s_acc)
                                                    break
                                except Exception as ex:
                                    _LOG.debug("gemini read candidate snapshot failed: %s", ex)
                                if snap is None:
                                    try:
                                        sc = getattr(ev, "serverContent", None)
                                        if sc:
                                            parts = getattr(sc, "parts", None)
                                            if parts:
                                                s_acc2: List[str] = []
                                                for p in parts:
                                                    ptext = getattr(p, "text", None)
                                                    if ptext:
                                                        s_acc2.append(str(ptext))
                                                if s_acc2:
                                                    snap = "".join(s_acc2)
                                    except Exception as ex:
                                        _LOG.debug("gemini read serverContent snapshot failed: %s", ex)
                                if snap is None:
                                    for attr in ("output_text", "model_output", "delta"):
                                        try:
                                            val = getattr(ev, attr, None)
                                            if isinstance(val, str) and val:
                                                snap = val
                                                break
                                        except Exception as ex:
                                            _LOG.debug("gemini read fallback attr failed: %s", ex)
                                if isinstance(snap, str) and snap:
                                    prev = accum
                                    if snap.startswith(prev):
                                        delta = snap[len(prev):]
                                    else:
                                        overlap = 0
                                        max_check = min(len(prev), SNAPSHOT_MAX_CHECK)
                                        for k in range(max_check, 0, -1):
                                            if prev.endswith(snap[:k]):
                                                overlap = k
                                                break
                                        delta = snap[overlap:]
                                    if delta:
                                        _emit_delta(delta)
                                    accum = snap
                                    stream_holder["final_text"] = accum
                            # Threshold warnings for investigating truncation proximity
                            if isinstance(_resolved_cap, int) and _resolved_cap > 0:
                                approx_tokens = len(accum) / 4
                                if not warn70 and approx_tokens >= 0.7 * _resolved_cap:
                                    warn70 = True
                                    _LOG.warning({
                                        "evt": "gemini_cap_70pct", "job_id": job_id, "model": model, "role": _meta_role,
                                        "approx_tokens": int(approx_tokens), "max_output_tokens": _resolved_cap
                                    })
                                if not warn95 and approx_tokens >= 0.95 * _resolved_cap:
                                    warn95 = True
                                    _LOG.warning({
                                        "evt": "gemini_cap_95pct", "job_id": job_id, "model": model, "role": _meta_role,
                                        "approx_tokens": int(approx_tokens), "max_output_tokens": _resolved_cap
                                    })
                        except Exception as _e:
                            try:
                                _LOG.debug("gemini delta calc error: %s", _e)
                            except Exception as ex:
                                _LOG.debug("gemini delta calc nested log failed: %s", ex)
                            break
                except Exception as ex:
                    _LOG.debug("gemini pump top-level error: %s", ex)
                finally:
                    # Attempt Gemini usage extraction (provider count_tokens) before signaling stream end
                    try:
                        # Only attempt if we have not already stored usage for this job
                        if _USAGE_REAL.get(str(job_id)) in (None, (None, None)):
                            from google import genai as _ggenai  # type: ignore
                            try:
                                # Best-effort token counting (prompt only available here); completion from accumulated text
                                ct = client.models.count_tokens(model=model, contents=user_prompt)
                                # Library may expose fields under different attribute names; access defensively
                                p_tok = getattr(ct, "total_tokens", None) or getattr(ct, "totalTokens", None)
                                if p_tok is None:
                                    # Some versions may return a 'tokens' list length
                                    toks_list = getattr(ct, "tokens", None)
                                    if toks_list is not None:
                                        try:
                                            p_tok = len(toks_list)
                                        except Exception:
                                            p_tok = None
                                final_txt = stream_holder.get("final_text") or ""
                                c_tok = int(len(final_txt) / 4) if final_txt else None
                                if p_tok is not None or c_tok is not None:
                                    try:
                                        _LOG.warning({
                                            "evt": "gemini_count_tokens_stream",
                                            "job_id": job_id,
                                            "model": model,
                                            "prompt_tokens": p_tok,
                                            "completion_tokens_est": c_tok,
                                        })
                                    except Exception:
                                        pass
                                    # Treat count_tokens as provider supplied (store) but completion still heuristic
                                    _store_usage(job_id, int(p_tok) if p_tok is not None else None, c_tok)
                            except Exception as _ct_ex:  # pragma: no cover
                                try:
                                    _LOG.debug({"evt": "gemini_count_tokens_fail", "job_id": job_id, "err": str(_ct_ex)})
                                except Exception:
                                    pass
                    except Exception as _outer_ct_ex:  # pragma: no cover
                        try:
                            _LOG.debug({"evt": "gemini_usage_outer_fail", "job_id": job_id, "err": str(_outer_ct_ex)})
                        except Exception:
                            pass
                    loop.call_soon_threadsafe(q.put_nowait, None)
                    def _final_log():
                        try:
                            final_txt = stream_holder.get("final_text") or ""
                            # Compute a content hash for debugging (not PII)
                            import hashlib
                            content_hash = hashlib.sha256(final_txt.encode('utf-8')).hexdigest()[:16] if final_txt else ""
                            _LOG.warning({
                                "evt": "gemini_stream_final",
                                "job_id": job_id,
                                "model": model,
                                "role": _meta_role,
                                "chars": len(final_txt),
                                "approx_tokens_est": int(len(final_txt) / 4) if final_txt else 0,
                                "max_output_tokens": _resolved_cap,
                                "truncated_guess": (True if _resolved_cap and len(final_txt) / 4 >= (float(_resolved_cap) * 0.95) else False),
                                "content_hash": content_hash,
                                "finish_reasons": sorted(list(finish_reasons)) if finish_reasons else [],
                            })
                            for fr in finish_reasons:
                                if fr and fr.lower() not in ("stop", "finished"):
                                    _LOG.warning({
                                        "evt": "gemini_finish_reason",
                                        "job_id": job_id,
                                        "model": model,
                                        "role": _meta_role,
                                        "finish_reason": fr,
                                    })
                        except Exception as ex:
                            _LOG.debug("gemini final stream log failed: %s", ex)
                    loop.call_soon_threadsafe(_final_log)

            def _close_gem() -> None:
                try:
                    s = stream_holder.get("stream")
                    close = getattr(s, "close", None) if s is not None else None
                    if callable(close):
                        close()  # type: ignore[misc]
                except Exception as ex:
                    _LOG.debug("gemini _close_gem failed: %s", ex)

            def _abort_gem() -> None:
                _cancel()
                _close_gem()

            register_abort(job_id, _abort_gem)

            import threading
            t = threading.Thread(target=_pump, name=f"gemini-pump-{job_id}", daemon=True)
            t.start()

            while True:
                if cancel_event.is_set():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    await asyncio.sleep(BACKPRESSURE_SLEEP_S)
                    continue
                if item is None:
                    break
                yield item
            try:
                _close_gem()
            except Exception as ex:
                _LOG.debug("gemini close after loop failed: %s", ex)
            return
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("gemini streaming not available, fallback to non-streaming: %s", ex)
        # Non-streaming fallback: generate full text and emit in small chunks
        resp = None
        try:
            resp = client.models.generate_content(model=model, contents=user_prompt, config=gen_cfg)
            text = getattr(resp, "text", "") or ""
            if not text:
                # Attempt to reconstruct from candidates->content.parts text
                try:
                    cands = getattr(resp, "candidates", None)
                    acc: List[str] = []
                    if cands:
                        for c in cands:
                            content_obj = getattr(c, "content", None)
                            parts = None
                            if content_obj is not None:
                                parts = getattr(content_obj, "parts", None)
                            if parts:
                                for p in parts:
                                    ptext = getattr(p, "text", None)
                                    if ptext:
                                        acc.append(str(ptext))
                    if acc:
                        text = "".join(acc)
                except Exception as ex:
                    _LOG.debug("gemini gen candidates build failed: %s", ex)
        except Exception as ex:
            import logging as _log
            _log.getLogger(__name__).debug("gemini non-streaming failed: %s", ex)
            text = ""
        if text:
            # Abort-aware chunking
            CH = 80
            for i in range(0, len(text), CH):
                if cancel_event.is_set():
                    break
                yield text[i : i + CH]
                await asyncio.sleep(0)
            # Attempt Gemini usage metadata extraction (non-streaming only)
            try:
                if 'resp' in locals():
                    um = getattr(resp, "usage_metadata", None) or getattr(resp, "usageMetadata", None)
                    if um:
                        p = getattr(um, "prompt_token_count", None) or getattr(um, "promptTokenCount", None)
                        c = getattr(um, "candidates_token_count", None) or getattr(um, "candidatesTokenCount", None)
                        if p is not None or c is not None:
                            try:
                                p_i = int(p) if p is not None else None
                            except Exception:
                                p_i = None
                            try:
                                c_i = int(c) if c is not None else None
                            except Exception:
                                c_i = None
                            _store_usage(job_id, p_i, c_i)
            except Exception as ex:
                _LOG.debug("gemini usage metadata fetch failed: %s", ex)

    # Select provider generator
    if prov == "openai":
        agen = _openai_stream()
    elif prov == "anthropic":
        agen = _anthropic_stream()
    elif prov == "gemini":
        agen = _gemini_stream()
    elif prov == "xai":
        agen = _xai_stream()
    else:
        raise RuntimeError(f"Unknown provider {provider}")

    # First-byte / stall timeout loop
    first_timeout = first_byte_ms / 1000.0
    stall_timeout = stall_ms / 1000.0

    # Optional external cancel watcher (e.g., Redis cancel:{job_id})
    watcher_task: Optional[asyncio.Task] = None
    if external_cancel is not None and callable(external_cancel):
        async def _watch_cancel() -> None:
            try:
                try:
                    _LOG.info({"evt": "external_cancel_watch_start", "job_id": job_id})
                except Exception as ex:
                    _LOG.debug("external_cancel_watch_start warn failed: %s", ex)
                while True:
                    try:
                        if await external_cancel():
                            try:
                                _LOG.warning({"evt": "external_cancel_trigger", "job_id": job_id})
                            except Exception as ex:
                                _LOG.debug("external_cancel_trigger warn failed: %s", ex)
                            _cancel()
                            return
                    except Exception as ex:
                        # Best-effort watcher
                        _LOG.debug("external_cancel watcher loop error: %s", ex)
                    await asyncio.sleep(IDLE_SLEEP_S)
            except asyncio.CancelledError:
                try:
                    _LOG.info({"evt": "external_cancel_watch_stop", "job_id": job_id})
                except Exception as ex:
                    _LOG.debug("external_cancel_watch_stop warn failed: %s", ex)
                return
        watcher_task = asyncio.create_task(_watch_cancel())

    # Register a default abort (no-op) so /cancel can flip the event even before provider opens
    # Do not override a provider-specific abort that may have already been registered.
    if job_id not in _ABORTS:
        register_abort(job_id, _cancel)
    anext = agen.__anext__
    try:
        # Use the standard timeout loop for all providers (including Gemini).
        # The previous Gemini-specific preemptive race could spuriously switch
        # to a cancel path; we now rely on explicit timeout and cancel checks.
        use_preempt = False
        while True:
            if use_preempt:
                # Race next token vs cancellation for responsive aborts (Gemini only)
                timeout = (stall_timeout if saw_first else first_timeout)
                async def _await_next():
                    return await anext()
                next_task = asyncio.create_task(_await_next())
                cancel_task = asyncio.create_task(cancel_event.wait())
                try:
                    done, pending = await asyncio.wait({next_task, cancel_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
                    if not done:
                        # Timeout
                        for t in (next_task, cancel_task):
                            t.cancel()
                            try:
                                await t
                            except Exception as ex:
                                _LOG.debug("gemini await pending task failed: %s", ex)
                        if not saw_first:
                            try:
                                _LOG.warning({"evt": "stall_before_first", "job_id": job_id, "provider": prov, "model": model})
                            except Exception as ex:
                                _LOG.debug("stall_before_first warn failed: %s", ex)
                            raise StallBeforeFirstByte()
                        raise asyncio.TimeoutError("stall_timeout")
                    # If both completed, prefer the next token (natural completion) over cancel
                    if cancel_task in done and cancel_task.done() and next_task.done():
                        try:
                            tok = await next_task
                        except StopAsyncIteration:
                            return
                    elif cancel_task in done and cancel_task.done():
                        # Cancellation signalled and next not done: abort provider await
                        if not next_task.done():
                            next_task.cancel()
                            try:
                                await next_task
                            except Exception as ex:
                                _LOG.debug("gemini cancel next_task await failed: %s", ex)
                        else:
                            try:
                                await next_task
                            except Exception as ex:
                                _LOG.debug("gemini await next_task failed: %s", ex)
                        try:
                            abort_job(job_id)
                        except Exception as ex:
                            _LOG.debug("abort_job during cancel failed: %s", ex)
                        raise asyncio.CancelledError()
                    # Otherwise we have a token or StopAsyncIteration
                    try:
                        tok = await next_task
                    except StopAsyncIteration:
                        # End of stream
                        return
                finally:
                    # Ensure the non-selected task is cleaned up
                    for t in (next_task, cancel_task):
                        if not t.done():
                            t.cancel()
                            try:
                                await t
                            except Exception as ex:
                                _LOG.debug("cleanup await task failed: %s", ex)
            else:
                # Standard loop for all providers with timeouts and explicit cancel checks
                if cancel_event.is_set():
                    try:
                        _LOG.info({"evt": "cancel_raise", "where": "pre_wait", "job_id": job_id, "saw_first": saw_first})
                    except Exception as ex:
                        _LOG.debug("cancel_raise pre_wait warn failed: %s", ex)
                    raise asyncio.CancelledError()
                try:
                    tok = await asyncio.wait_for(anext(), timeout=(stall_timeout if saw_first else first_timeout))
                except asyncio.TimeoutError:
                    if not saw_first:
                        # Stall before first byte
                        try:
                            _LOG.warning({"evt": "stall_before_first", "job_id": job_id, "provider": prov, "model": model})
                        except Exception as ex:
                            _LOG.debug("stall_before_first warn failed: %s", ex)
                        raise StallBeforeFirstByte()
                    # Stall after streaming began
                    raise asyncio.TimeoutError("stall_timeout")
                except StopAsyncIteration:
                    # If cancellation was requested, propagate as CancelledError so callers can record cancel state
                    if cancel_event.is_set():
                        try:
                            _LOG.info({"evt": "cancel_raise", "where": "stop_iteration_after", "job_id": job_id, "saw_first": saw_first})
                        except Exception as ex:
                            _LOG.debug("cancel_raise stop_iteration_after warn failed: %s", ex)
                        raise asyncio.CancelledError()
                    return
                if cancel_event.is_set():
                    # Propagate cancellation so worker marks job as cancelled (not OK)
                    try:
                        _LOG.info({"evt": "cancel_raise", "where": "loop_after_token", "job_id": job_id, "saw_first": saw_first})
                    except Exception as ex:
                        _LOG.debug("cancel_raise loop_after_token warn failed: %s", ex)
                    raise asyncio.CancelledError()

            if tok is None:
                continue
            s = str(tok)
            if not s:
                continue
            saw_first = True
            # Stop-marker detection across chunk boundaries
            emit = s
            tail_check = (buffer_tail + s)
            hit = None
            for m in stops:
                if m and m in tail_check:
                    hit = m
                    break
            if hit is not None:
                # Clip output up to the marker occurrence
                idx = tail_check.find(hit)
                combined = tail_check[:idx]
                # Yield only the part from this chunk corresponding to combined beyond previous tail
                start_in_chunk = max(0, len(buffer_tail))
                remainder = combined[start_in_chunk:]
                if remainder:
                    yield remainder
                try:
                    _LOG.warning({
                        "evt": "stop_marker_triggered",
                        "job_id": job_id,
                        "provider": prov,
                        "model": model,
                        "marker": hit,
                        "emitted_chars": len(combined),
                    })
                except Exception:
                    pass
                return
            # No stop marker: update tail (keep last len of longest stop)
            max_stop = max((len(m) for m in stops), default=0)
            buffer_tail = tail_check[-max_stop:]
            yield emit
    except asyncio.CancelledError:
        # Ensure provider resources are closed via abort function
        try:
            abort_job(job_id)
        except Exception as ex:
            _LOG.debug("abort_job in CancelledError failed: %s", ex)
        try:
            _LOG.info({"evt": "cancel_caught", "job_id": job_id})
        except Exception as ex:
            _LOG.debug("cancel_caught warn failed: %s", ex)
        raise
    finally:
        if watcher_task is not None:
            try:
                watcher_task.cancel()
                with contextlib.suppress(Exception):
                    await watcher_task
            except Exception as ex:
                _LOG.debug("watcher_task cancel/await failed: %s", ex)
