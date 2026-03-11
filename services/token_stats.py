from __future__ import annotations

"""Token statistics helpers for real vs estimated counts.

Currently only estimation-based prompt_tokens / completion_tokens are used in pricing.
Real provider-reported columns (prompt_tokens_real, completion_tokens_real)
are being backfilled to 0 and populated prospectively. We should ignore zero real values when
computing any aggregate so that backfilled rows do not skew metrics.
"""
from decimal import Decimal
from typing import Sequence, Dict, Any


def average_real_tokens(rows: Sequence[Dict[str, Any]]) -> dict[str, Decimal | int]:
    """Compute averages over real token columns ignoring zeros.

    rows: iterable of dicts with keys prompt_tokens_real, completion_tokens_real.
    Returns { 'avg_prompt_tokens_real': Decimal, 'avg_completion_tokens_real': Decimal, 'n': int }
    Only rows with (prompt_tokens_real > 0 or completion_tokens_real > 0) are included.
    If no qualifying rows, avgs are 0.
    """
    p_total = Decimal(0)
    c_total = Decimal(0)
    n = 0
    for r in rows:
        try:
            p = int(r.get('prompt_tokens_real') or 0)
            c = int(r.get('completion_tokens_real') or 0)
        except Exception:
            continue
        if p <= 0 and c <= 0:
            continue
        p_total += p
        c_total += c
        n += 1
    if n == 0:
        return {"avg_prompt_tokens_real": Decimal(0), "avg_completion_tokens_real": Decimal(0), "n": 0}
    return {
        "avg_prompt_tokens_real": (p_total / Decimal(n)) if n else Decimal(0),
        "avg_completion_tokens_real": (c_total / Decimal(n)) if n else Decimal(0),
        "n": n,
    }
