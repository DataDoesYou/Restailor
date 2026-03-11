from __future__ import annotations

from typing import Optional, Any
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy.orm import Session

from restailor.models import Charge


def median_last100_price(
    session: Session,
    *,
    request_types: Optional[list[str]] = None,
    exclude_types: Optional[list[str]] = None,
    global_scope: bool = True,
    user_id: Optional[int] = None,
    output_models: Optional[int] = None,
    include_test_rows: bool = False,
) -> dict[str, Any]:
    """
    Median end-user price (price_to_user_usd) over the most recent 100 qualifying
    charges. When request_types is provided, only those types are included.
    When exclude_types is provided, those types are excluded. By default,
    all request types are considered.

        Qualifying rows follow the same rules as averages:
            - prompt_tokens > 0 and completion_tokens > 0
            - When include_test_rows is False, only rows with is_test = false are included

    Returns: {"median_price": Decimal, "n": int}
    If no rows match, returns median_price=Decimal('0') and n=0.
    """
    c = Charge.__table__
    where_clauses = [
        c.c.prompt_tokens > 0,
        c.c.completion_tokens > 0,
    ]
    if not include_test_rows:
        where_clauses.append(c.c.is_test == sa.false())
    if request_types:
        where_clauses.append(c.c.request_type.in_([str(t) for t in request_types]))
    if exclude_types:
        where_clauses.append(~c.c.request_type.in_([str(t) for t in exclude_types]))
    if not global_scope:
        if user_id is None:
            return {"median_price": Decimal("0"), "n": 0}
        where_clauses.append(c.c.user_id == int(user_id))
    if output_models is not None:
        # Filter by number of output models (post-migration column name)
        where_clauses.append(c.c.output_models == int(output_models))

    # Prefer real prices when available, fallback to estimated
    price_col = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd).label("effective_price")
    
    ranked = sa.select(
        price_col,
        c.c.created_at,
        sa.func.row_number().over(order_by=c.c.created_at.desc()).label("rn"),
    ).where(sa.and_(*where_clauses)).subquery("ranked_prices")

    limited = sa.select(ranked.c.effective_price).where(ranked.c.rn <= 100).subquery("limited_prices")

    agg = sa.select(
        sa.func.percentile_cont(0.5).within_group(limited.c.effective_price).label("median_price"),
        sa.func.count().label("n"),
    )

    row = session.execute(agg).one_or_none()
    if not row:
        return {"median_price": Decimal("0"), "n": 0}
    med = getattr(row, "median_price", None)
    n = int(getattr(row, "n", 0) or 0)
    return {"median_price": Decimal(med) if med is not None else Decimal("0"), "n": n}


def trimmed_average_last100_price(
    session: Session,
    *,
    request_types: Optional[list[str]] = None,
    exclude_types: Optional[list[str]] = None,
    global_scope: bool = True,
    user_id: Optional[int] = None,
    output_models: Optional[int] = None,
    trim_frac: float = 0.10,
    include_test_rows: bool = False,
) -> dict[str, Any]:
    """
    Compute a trimmed mean of price_to_user_usd over the most recent 100 qualifying charges.

    - Filters: prompt_tokens>0, completion_tokens>0
    - When include_test_rows is False, only rows with is_test=false are included
    - Include only request_types (if provided) and exclude any in exclude_types
    - If trim_frac in [0, 0.5): drop trim_frac from each tail after sorting by price

    Returns: {"avg_price": Decimal, "n": int, "n_used": int}
    """
    c = Charge.__table__
    where_clauses = [
        c.c.prompt_tokens > 0,
        c.c.completion_tokens > 0,
    ]
    if not include_test_rows:
        where_clauses.append(c.c.is_test == sa.false())
    if request_types:
        where_clauses.append(c.c.request_type.in_([str(t) for t in request_types]))
    if exclude_types:
        where_clauses.append(~c.c.request_type.in_([str(t) for t in exclude_types]))
    if not global_scope:
        if user_id is None:
            return {"avg_price": Decimal("0"), "n": 0, "n_used": 0}
        where_clauses.append(c.c.user_id == int(user_id))
    if output_models is not None:
        where_clauses.append(c.c.output_models == int(output_models))

    # Prefer real prices when available, fallback to estimated
    price_col = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd).label("effective_price")
    
    ranked = sa.select(
        price_col,
        c.c.created_at,
        sa.func.row_number().over(order_by=c.c.created_at.desc()).label("rn"),
    ).where(sa.and_(*where_clauses)).subquery("ranked_prices")

    limited = sa.select(ranked.c.effective_price).where(ranked.c.rn <= 100)
    rows = session.execute(limited).all()
    vals = [Decimal(getattr(r, "effective_price")) for r in rows if getattr(r, "effective_price", None) is not None]
    n = len(vals)
    if n == 0:
        return {"avg_price": Decimal("0"), "n": 0, "n_used": 0}
    # Trim
    try:
        tf = float(trim_frac)
    except Exception:
        tf = 0.0
    tf = 0.0 if tf < 0 else (0.49 if tf >= 0.5 else tf)
    vals.sort()
    k = int(n * tf)
    used = vals[k:n - k] if (n - 2 * k) > 0 else vals
    n_used = len(used)
    avg = (sum(used, start=Decimal("0")) / Decimal(n_used)) if n_used > 0 else Decimal("0")
    return {"avg_price": avg, "n": n, "n_used": n_used}


def last100_avg_by_request_and_model(
    session: Session,
    *,
    global_scope: bool,
    user_id: Optional[int] = None,
    model_filter: Optional[str] = None,
    request_type_filter: Optional[str] = None,
    output_models: Optional[int] = None,
    include_test_rows: bool = False,
) -> list[dict[str, Any]]:
    """
    Compute averages over the most recent 100 charges per (request_type, model).

    Returns rows as dicts: {request_type, model, avg_price: Decimal, n: int}
    If global_scope is False, filter by the provided user_id.
    Optional filters: model_filter, request_type_filter.
    When include_test_rows is False, only rows with is_test=false are considered.
    """
    c = Charge.__table__
    where_clauses = []
    if not global_scope:
        if user_id is None:
            return []
        where_clauses.append(c.c.user_id == int(user_id))
    if model_filter:
        where_clauses.append(c.c.model == str(model_filter))
    if request_type_filter:
        where_clauses.append(c.c.request_type == str(request_type_filter))
    if output_models is not None:
        where_clauses.append(c.c.output_models == int(output_models))
    # Only include real, paid charges with positive token counts
    if not include_test_rows:
        where_clauses.append(c.c.is_test == sa.false())
    where_clauses.append(c.c.prompt_tokens > 0)
    where_clauses.append(c.c.completion_tokens > 0)

    # Prefer real prices when available, fallback to estimated
    price_col = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd).label("effective_price")
    
    base = sa.select(
        c.c.request_type,
        c.c.model,
        price_col,
        c.c.created_at,
        sa.func.row_number().over(
            partition_by=(c.c.request_type, c.c.model),
            order_by=c.c.created_at.desc(),
        ).label("rn"),
    )
    if where_clauses:
        base = base.where(sa.and_(*where_clauses))

    base = base.subquery("ranked")

    limited = sa.select(base.c.request_type, base.c.model, base.c.effective_price).where(base.c.rn <= 100)
    limited = limited.subquery("limited")

    agg = sa.select(
        limited.c.request_type,
        limited.c.model,
        sa.func.avg(limited.c.effective_price).label("avg_price"),
        sa.func.count().label("n"),
    ).group_by(limited.c.request_type, limited.c.model).order_by(limited.c.request_type.asc(), limited.c.model.asc())

    rows = session.execute(agg).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        req_t = getattr(r, "request_type", None)
        model = getattr(r, "model", None)
        avg_price = getattr(r, "avg_price", None)
        n = getattr(r, "n", 0)
        out.append({
            "request_type": str(req_t),
            "model": str(model),
            "avg_price": Decimal(avg_price) if avg_price is not None else Decimal("0"),
            "n": int(n or 0),
        })
    return out
