"""
Streaming post-processor clamp with runtime stop_markers.

This module provides a thin wrapper around services.postprocess.wrap_stream to:
- combine legacy default stop sequences with a runtime end_marker
- expose a stable entry point for streaming clamps

Behavior:
- Maintains a lookback window up to the longest stop marker
- Emits text up to the earliest marker and never emits the marker itself
- Optionally performs echo clamp (ratio / quoted char caps) and yields a final
  token with an ellipsis followed by a done event with {clamped: true}
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Iterable, List, Optional

from services.postprocess import wrap_stream as _wrap_stream


def build_stop_markers(defaults: Optional[Iterable[str]] = None, end_marker: Optional[str] = None) -> List[str]:
    out: List[str] = []
    for s in (defaults or []):
        if isinstance(s, str) and s:
            out.append(s)
    if isinstance(end_marker, str) and end_marker:
        out.append(end_marker)
    # de-dup while preserving order
    seen: set[str] = set()
    uniq: List[str] = []
    for s in out:
        if s not in seen:
            uniq.append(s); seen.add(s)
    return uniq or ["### END"]


async def clamp_stream(
    *,
    role: str,
    src_texts: List[str],
    agen: AsyncIterator[str],
    stop_markers: List[str],
    echo_ratio_cap: float | None = None,
    max_quoted_chars: int | None = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Delegate to wrap_stream with the provided runtime stop markers.

    Yields dict events with keys:
      - type: 'token' | 'done'
      - text: for token events
      - status/error/clamped/tokens_out_streamed for done events
    """
    async for ev in _wrap_stream(
        role=role,
        src_texts=src_texts,
        agen=agen,
        stop_markers=stop_markers,
        echo_ratio_cap=echo_ratio_cap,
        max_quoted_chars=max_quoted_chars,
        try_repair_json=None,
    ):
        yield ev
