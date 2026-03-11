from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator, Callable, Optional


def sse_event(event: Optional[str], data: dict | str) -> str:
    if isinstance(data, (dict, list)):
        payload = json.dumps(data)
    else:
        payload = str(data)
    if event:
        return f"event: {event}\n" + f"data: {payload}\n\n"
    return f"data: {payload}\n\n"


async def sse_stream_response(
    token_iter: AsyncIterator[str],
    *,
    keepalive_ms: int = 15000,
    suppress_tokens: bool = False,
    on_disconnect: Optional[Callable[[], None]] = None,
) -> AsyncIterator[bytes]:
    """Adapt a token iterator into SSE bytes with keepalives and done event.

    - Yields token events unless suppress_tokens is True.
    - Emits keepalive events every keepalive_ms when idle.
    - Emits a final 'done' event when iterator completes.
    - Calls on_disconnect if client disconnects (GeneratorExit/CancelledError).
    """
    keep_s = max(1.0, (keepalive_ms or 15000) / 1000.0)
    last = 0.0
    import time as _time

    try:
        async for tok in token_iter:
            if not suppress_tokens:
                yield sse_event("token", {"t": tok}).encode("utf-8")
            # reset keepalive timer on activity
            last = _time.monotonic()
            # give event loop a chance
            await asyncio.sleep(0)
            # opportunistic keepalive if long since last
            now = _time.monotonic()
            if now - last >= keep_s:
                last = now
                yield sse_event("keepalive", "ping").encode("utf-8")
        # normal completion
        yield sse_event("done", {"status": "completed"}).encode("utf-8")
    except (asyncio.CancelledError, GeneratorExit):
        if on_disconnect:
            try:
                on_disconnect()
            except Exception as ex:
                import logging as _log
                _log.getLogger(__name__).debug("sse_utils.on_disconnect callback failed: %s", ex)
        return
    except Exception as ex:
        # Send error then done:failed to close the stream cleanly
        try:
            yield sse_event("error", {"message": str(ex)}).encode("utf-8")
            yield sse_event("done", {"status": "failed", "error": str(ex)}).encode("utf-8")
        finally:
            return
