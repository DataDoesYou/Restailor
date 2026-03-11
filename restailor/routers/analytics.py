from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import time
import threading
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any, Literal, Optional
import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from restailor import auth as auth_dep
from restailor.db import SessionLocal
from restailor.models import Charge, CreditLedger, AnalyticsJobSnapshotState, User
from services.analytics_job_snapshot import ensure_snapshot_state

logger = logging.getLogger(__name__)


analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


def _normalize_dt(val: datetime | None) -> datetime | None:
    if not isinstance(val, datetime):
        return None
    try:
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    except Exception:
        return val

# --- In-process TTL cache for summary (per-worker) ---
_SUMMARY_CACHE_TTL_SEC = 300  # 5 minutes (historical data doesn't change frequently)
_summary_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_summary_cache_lock = threading.Lock()


# Local dependency wrapper to match project pattern
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fmt_usd(d: Decimal | int | float | None) -> str:
    try:
        dec = d if isinstance(d, Decimal) else Decimal(str(d or 0))
    except Exception:
        dec = Decimal("0")
    return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _tz_expr(col, tz: str | None):
    """Return an expression to convert timestamptz to desired timezone name for bucketing.

    For SQLite (tests) this is a no-op. For Postgres, use AT TIME ZONE text.
    """
    # Detect dialect name safely
    try:
        from sqlalchemy import text
        if tz and tz.strip():
            # Use SQL text for portability; caller must use date_bin/date_trunc on top.
            return sa.text(f"({col.key} AT TIME ZONE :tz)").bindparams(sa.bindparam("tz", tz))
    except Exception:
        pass
    return col


def _bucket_expr(dt_col, bucket: str, dialect_name: str | None = None, tz: str | None = None) -> Any:
    b = (bucket or "day").lower()
    if b not in {"hour", "day", "week", "month"}:
        b = "day"
    # Prefer date_trunc for Postgres; SQLite fallback: strftime formats
    if (dialect_name or "").lower().startswith("sqlite"):
        fmt = "%Y-%m-%d"
        if b == "hour":
            fmt = "%Y-%m-%d %H:00:00"
        elif b == "week":
            # approximate to Monday of week (SQLite)
            return sa.func.date(sa.func.strftime("%Y-%m-%d", dt_col), "weekday 1")
        elif b == "month":
            fmt = "%Y-%m-01"
        return sa.func.strftime(fmt, dt_col)
    # Postgres & others: date_trunc; apply timezone if provided
    expr = dt_col
    if tz and tz.strip():
        try:
            expr = sa.func.timezone(tz, dt_col)
        except Exception:
            expr = dt_col
    return sa.func.date_trunc(b, expr)


# ---- Helpers (module-private) ------------------------------------------------

def _parse_range(from_str: Optional[str], to_str: Optional[str], tz_str: Optional[str]) -> tuple[datetime, datetime, str]:
    """Parse inputs into UTC datetimes and choose a sensible bucket.

    Rules:
    - If both missing: [now-30d, now)
    - If only start: [start, now)
    - If only end: [end-30d, end)
    - Bucket by span: <=2d: hour; <=90d: day; <=400d: week; else: month
    """
    def _p(x: Optional[str]) -> Optional[datetime]:
        if not x:
            return None
        try:
            return datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None

    now = datetime.now(timezone.utc)
    start = _p(from_str)
    end = _p(to_str)
    if start is None and end is None:
        end = now
        start = end - timedelta(days=30)
    elif start is None and end is not None:
        start = end - timedelta(days=30)
    elif start is not None and end is None:
        end = now

    # At this point, both are not None
    assert start is not None and end is not None

    # Normalize order
    if start > end:
        start, end = end, start

    span = end - start
    if span <= timedelta(days=2):
        bucket = "hour"
    elif span <= timedelta(days=90):
        bucket = "day"
    elif span <= timedelta(days=400):
        bucket = "week"
    else:
        bucket = "month"
    return start, end, bucket


def _ensure_snapshot_state_fresh(session: Session, user_id: int) -> None:
    """Ensure analytics snapshot state rows are present and up to date."""
    if not user_id:
        return

    include_tests = bool(os.getenv("RUN_TESTS_VIA_SCRIPT"))
    if not include_tests:
        try:
            user_test_flag = session.execute(
                sa.select(User.is_test).where(User.id == user_id)
            ).scalar_one_or_none()
            include_tests = bool(user_test_flag)
        except Exception:
            include_tests = False

    try:
        ensure_snapshot_state(
            session,
            user_id,
            include_test_rows=include_tests,
            force=False,
            reason="analytics.ensure_snapshot_state_fresh",
            logger=logger,
            commit=True,
        )
    except Exception as ex:
        try:
            logger.warning("analytics.snapshot_rebuild_failed", exc_info=ex)
        except Exception:
            pass


def _snapshot_stage_expr(state_tbl: sa.Table):
    """Return SQL expression representing the effective stage label for analytics.

    Priority order: hired > offer > interviewing > applied (default).
    """
    return sa.case(
        (state_tbl.c.is_hired.is_(True), sa.literal("hired")),
        (state_tbl.c.is_offer.is_(True), sa.literal("offer")),
        (state_tbl.c.is_interviewing.is_(True), sa.literal("interviewing")),
        (state_tbl.c.is_applied.is_(True), sa.literal("applied")),
        else_=sa.literal("applied"),
    )


def _should_include_tests_for_user(session: Session, current_user, user_id: int) -> bool:
    include_tests = bool(os.getenv("RUN_TESTS_VIA_SCRIPT"))
    if not include_tests:
        try:
            include_tests = bool(getattr(current_user, "is_test", False))
        except Exception:
            include_tests = False
    if not include_tests and user_id:
        try:
            user_test_flag = session.execute(
                sa.select(User.is_test).where(User.id == user_id)
            ).scalar_one_or_none()
            include_tests = bool(user_test_flag)
        except Exception:
            include_tests = False
    return include_tests


def _fresh_current_balance(session: Session, user_id: int, include_tests: bool = False) -> tuple[int, str]:
    """Compute current balance directly from DB rows (no cache).

    Definition: sum(credit_ledger.delta_cents where is_test=false) - sum(round(charges.price_to_user_usd*100) where is_test=false)
    Never negative; format as $x.xx string.
    """
    l = CreditLedger.__table__
    c = Charge.__table__

    dep_filters = [l.c.user_id == user_id]
    if not include_tests:
        dep_filters.append(l.c.is_test == sa.false())
    dep_row = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(l.c.delta_cents), 0).label("dep"))
        .where(sa.and_(*dep_filters))
    ).one_or_none()
    # Sum charges using real price when available, else estimated
    _price_expr = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd)
    chg_filters = [c.c.user_id == user_id]
    if not include_tests:
        chg_filters.append(c.c.is_test == sa.false())
    chg_row = session.execute(
        sa.select(
            sa.func.coalesce(
                sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)), 0
            ).label("chg")
        ).where(sa.and_(*chg_filters))
    ).one_or_none()

    def _scalar(row, fallback_idx: int = 0) -> int:
        if row is None:
            return 0
        # Try named columns first, then positional
        for name in ("dep", "chg", "coalesce_1", "sum", "sum_1"):
            try:
                v = getattr(row, name)
                if v is not None:
                    return int(v or 0)
            except Exception:
                pass
        try:
            return int(row[fallback_idx] or 0)
        except Exception:
            return 0

    dep_total = _scalar(dep_row)
    chg_total = _scalar(chg_row)
    cents = dep_total - chg_total
    if cents < 0:
        cents = 0
    return cents, _fmt_usd(Decimal(cents) / Decimal(100))


def _requests_by_type(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    bucket: str,
    tz: Optional[str] = None,
    include_tests: bool = False,
):
    c = Charge.__table__
    dialect_name = getattr(getattr(session.bind, "dialect", None), "name", None) if getattr(session, "bind", None) else None
    bkt = _bucket_expr(c.c.created_at, bucket, dialect_name, tz).label("bucket")
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        bkt,
        c.c.request_type,
        sa.func.count().label("count"),
    ).where(sa.and_(*filters)).group_by(bkt, c.c.request_type).order_by(sa.text("bucket ASC"))
    return session.execute(stmt).all()


def _spend_by_type(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    include_tests: bool = False,
):
    c = Charge.__table__
    _price_expr = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd)
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        c.c.request_type,
        sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("cents"),
        sa.func.count().label("requests"),
    ).where(sa.and_(*filters)).group_by(c.c.request_type)
    return session.execute(stmt).all()


def _spend_by_model(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    include_tests: bool = False,
):
    c = Charge.__table__
    _price_expr = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd)
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        c.c.model,
        sa.func.count().label("requests"),
        sa.func.avg(_price_expr).label("avg_price_usd"),
        sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("cents"),
    ).where(sa.and_(*filters)).group_by(c.c.model)
    return session.execute(stmt).all()


def _multi_model_counts(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    include_tests: bool = False,
):
    c = Charge.__table__
    # Prefer model_count if present; fallback to output_models for older schemas
    try:
        model_count_col = getattr(c.c, "model_count")
    except Exception:
        model_count_col = None
    use_col = model_count_col or c.c.output_models
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        use_col.label("model_count"),
        sa.func.count().label("n"),
    ).where(sa.and_(*filters)).group_by(use_col)
    return session.execute(stmt).all()


def _tokens_by_model(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    include_tests: bool = False,
):
    c = Charge.__table__
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        c.c.model,
        sa.func.avg(c.c.prompt_tokens).label("avg_prompt"),
        sa.func.avg(c.c.completion_tokens).label("avg_completion"),
    ).where(sa.and_(*filters)).group_by(c.c.model)
    return session.execute(stmt).all()


def _latency_series(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    bucket: str,
    tz: Optional[str] = None,
    include_tests: bool = False,
):
    # avg jobs.latency_ms grouped by bucket for job_ids in charges
    from restailor.models import Job  # local import
    c = Charge.__table__
    j = Job.__table__
    dialect_name = getattr(getattr(session.bind, "dialect", None), "name", None) if getattr(session, "bind", None) else None
    bkt = _bucket_expr(c.c.created_at, bucket, dialect_name, tz).label("bucket")
    filters = [c.c.user_id == user_id]
    if start is not None:
        filters.append(c.c.created_at >= start)
    if end is not None:
        filters.append(c.c.created_at < end)
    if not include_tests:
        filters.append(c.c.is_test == sa.false())
    stmt = sa.select(
        bkt,
        sa.func.avg(j.c.latency_ms).label("avg_ms"),
    ).select_from(
        c.join(j, c.c.job_id == j.c.id, isouter=True)
    ).where(sa.and_(*filters)).group_by(bkt).order_by(sa.text("bucket ASC"))
    return session.execute(stmt).all()


def _balance_series(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    bucket: str,
    tz: Optional[str] = None,
    include_tests: bool = False,
):
    """Compute end-of-bucket user balance using deposits minus charges.

    Contract:
    - opening_balance = (sum deposits before start) - (sum charges before start)
    - for each bucket: delta = deposits(bucket) - charges(bucket)
    - running_balance += delta (never below 0)
    - return rows ordered by bucket with bucket, delta_cents, running_cents

    Bucketing honors the provided timezone when supported by the DB. The
    returned "bucket" value is the database's date_trunc/strftime result (as a
    string via SQLAlchemy row repr), which the client already handles.
    """

    l = CreditLedger.__table__
    c = Charge.__table__

    # Detect dialect for bucketing expression
    try:
        dialect_name = getattr(getattr(session.bind, "dialect", None), "name", None) if getattr(session, "bind", None) else None
    except Exception:
        dialect_name = None

    # Bucket expressions for both tables
    l_bucket = _bucket_expr(l.c.created_at, bucket, dialect_name, tz).label("bucket")
    c_bucket = _bucket_expr(c.c.created_at, bucket, dialect_name, tz).label("bucket")

    # Deposits per bucket (credit ledger)
    dep_rows = session.execute(
        sa.select(
            l_bucket,
            sa.func.sum(l.c.delta_cents).label("deposits_cents"),
        ).where(
            sa.and_(
                l.c.user_id == user_id,
                l.c.created_at >= start,
                l.c.created_at < end,
            )
        ).group_by(l_bucket).order_by(sa.text("bucket ASC"))
    ).all()

    # Charges per bucket (priced usage)
    _price_expr = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd)
    chg_filters = [c.c.user_id == user_id]
    if start is not None:
        chg_filters.append(c.c.created_at >= start)
    if end is not None:
        chg_filters.append(c.c.created_at < end)
    if not include_tests:
        chg_filters.append(c.c.is_test == sa.false())
    chg_rows = session.execute(
        sa.select(
            c_bucket,
            sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("charges_cents"),
        ).where(sa.and_(*chg_filters)).group_by(c_bucket).order_by(sa.text("bucket ASC"))
    ).all()

    # Opening balance before the window: deposits before start minus charges before start
    dep_before_row = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(l.c.delta_cents), 0)).where(
            sa.and_(l.c.user_id == user_id, l.c.created_at < start)
        )
    ).one_or_none()
    chg_before_filters = [c.c.user_id == user_id, c.c.created_at < start]
    if not include_tests:
        chg_before_filters.append(c.c.is_test == sa.false())
    chg_before_row = session.execute(
        sa.select(sa.func.coalesce(sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)), 0)).where(
            sa.and_(*chg_before_filters)
        )
    ).one_or_none()

    def _row_scalar(row, attr_candidates: list[str]) -> int:
        if row is None:
            return 0
        for a in attr_candidates:
            try:
                v = getattr(row, a, None)
                if v is not None:
                    return int(v or 0)
            except Exception:
                pass
        try:
            return int(row[0] or 0)
        except Exception:
            return 0

    dep_before = _row_scalar(dep_before_row, ["coalesce_1", "sum_1"])
    chg_before = _row_scalar(chg_before_row, ["coalesce_1", "sum_1"])
    opening_cents = dep_before - chg_before
    if opening_cents < 0:
        # Enforce invariant: balances never negative
        opening_cents = 0

    # Merge per-bucket deposits and charges
    buckets: dict[str, dict[str, int]] = {}
    for r in dep_rows:
        b = str(getattr(r, "bucket"))
        buckets.setdefault(b, {"deposits_cents": 0, "charges_cents": 0})
        buckets[b]["deposits_cents"] = int(getattr(r, "deposits_cents", 0) or 0)
    for r in chg_rows:
        b = str(getattr(r, "bucket"))
        buckets.setdefault(b, {"deposits_cents": 0, "charges_cents": 0})
        buckets[b]["charges_cents"] = int(getattr(r, "charges_cents", 0) or 0)

    # Compute running balances ordered by bucket
    ordered_keys = sorted(buckets.keys())
    running = opening_cents
    out: list[dict[str, Any]] = []
    for k in ordered_keys:
        dep = int(buckets[k].get("deposits_cents", 0) or 0)
        chg = int(buckets[k].get("charges_cents", 0) or 0)
        delta = dep - chg
        running = running + delta
        if running < 0:
            # Guard against rounding/slips; chart must never show negative
            running = 0
        out.append({
            "bucket": k,
            "delta_cents": delta,
            "running_cents": running,
            "deposits_cents": dep,
            "charges_cents": chg,
        })

    # Return list of simple objects resembling a DB result
    class _Row:
        def __init__(self, d: dict[str, Any]):
            self.bucket = d["bucket"]
            self.delta_cents = d["delta_cents"]
            self.running_cents = d["running_cents"]
            self.deposits_cents = d["deposits_cents"]
            self.charges_cents = d["charges_cents"]

    return [ _Row(d) for d in out ]


def _recent_ledger(session: Session, user_id: int, start: datetime, end: datetime, limit: int = 50):
    l = CreditLedger.__table__
    stmt = sa.select(
        l.c.id,
        l.c.created_at,
        l.c.delta_cents,
    l.c.type,
    ).where(
        sa.and_(
            l.c.user_id == user_id,
            l.c.created_at >= start,
            l.c.created_at < end,
        )
    ).order_by(l.c.created_at.desc()).limit(max(1, min(int(limit or 50), 200)))
    return session.execute(stmt).all()


class SeriesPoint(BaseModel):
    bucket: str
    count: int
    spend_usd: str


class SummaryResponse(BaseModel):
    series: list[SeriesPoint]
    by_type: dict[str, dict[str, Any]]
    by_model: dict[str, dict[str, Any]]
    multi_model: dict[str, int]
    token_mix: dict[str, int]
    latency: dict[str, float]
    balance_timeline: list[dict[str, Any]]


@analytics_router.get("/summary")
async def summary(
    db: Annotated[Session, Depends(get_db)],
    current_user=Depends(auth_dep.get_current_user),
    # filters
    start: Optional[str] = Query(default=None, alias="from", description="ISO start (inclusive)"),
    end: Optional[str] = Query(default=None, alias="to", description="ISO end (exclusive)"),
    period: Optional[str] = Query(default=None, description="preset: 7d|30d|90d (used if from/to missing)"),
    bucket: Optional[str] = Query(default=None, description="hour|day|week|month (auto if omitted)"),
    tz: Optional[str] = Query(default=None, description="IANA tz name"),
    request_type: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    recent_limit: int = Query(default=50, ge=1, le=500, description="Recent ledger rows limit"),
):
    """Return compact analytics for the dashboard.

    Scope: current user only (bearer). Keep results small via bucketing and time filters.
    """
    c = Charge.__table__
    # Parse range and bucket
    dt_start, dt_end, auto_bucket = _parse_range(start, end, tz)
    use_bucket = (bucket or auto_bucket).lower()

    # Cache key: user + time range + bucket + filters + tz
    uid = int(getattr(current_user, "id", 0))
    include_tests = _should_include_tests_for_user(db, current_user, uid)
    key_parts = [
        str(uid),
        (dt_start.isoformat() if isinstance(dt_start, datetime) else str(dt_start)),
        (dt_end.isoformat() if isinstance(dt_end, datetime) else str(dt_end)),
        use_bucket,
        str(request_type or ""),
    str(model or ""),
    str(tz or ""),
    "tests" if include_tests else "prod",
    ]
    cache_key = "|".join(key_parts)
    now_ts = time.time()
    try:
        with _summary_cache_lock:
            ts_resp = _summary_cache.get(cache_key)
            if ts_resp and (now_ts - ts_resp[0] <= _SUMMARY_CACHE_TTL_SEC):
                # Always refresh current balance fields from DB even when returning cached summary
                try:
                    fresh_cents, fresh_usd = _fresh_current_balance(db, uid, include_tests=include_tests)
                    resp = dict(ts_resp[1])
                    resp["current_balance_cents"] = fresh_cents
                    resp["balance_usd"] = fresh_usd
                    return resp
                except Exception:
                    # Fallback to cached if fresh lookup fails
                    return ts_resp[1]
    except Exception:
        pass

    where = [
        c.c.user_id == uid,
        c.c.prompt_tokens > 0,
        c.c.completion_tokens > 0,
    ]
    if not include_tests:
        where.append(c.c.is_test == sa.false())
    if dt_start:
        where.append(c.c.created_at >= dt_start)
    if dt_end:
        where.append(c.c.created_at < dt_end)
    if request_type:
        where.append(c.c.request_type == str(request_type))
    if model:
        where.append(c.c.model == str(model))
    # Request/model filters (use available indices)
    if request_type:
        where.append(c.c.request_type == str(request_type))
    if model:
        where.append(c.c.model == str(model))

    # Bucketing
    dt_col = c.c.created_at
    try:
        _bind = getattr(db, "bind", None)
        _dialect = getattr(_bind, "dialect", None)
        _name = getattr(_dialect, "name", None)
        dialect_name = str(_name) if _name is not None else None
    except Exception:
        dialect_name = None
    bucket_expr = _bucket_expr(dt_col, use_bucket, dialect_name, tz)

    # Time series: requests and spend
    _price_expr = sa.func.coalesce(c.c.price_to_user_usd_real, c.c.price_to_user_usd)
    series_stmt = sa.select(
        bucket_expr.label("bucket"),
        sa.func.count().label("count"),
        sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("cents"),
    ).where(sa.and_(*where)).group_by(bucket_expr).order_by(sa.text("bucket ASC"))

    series_rows = db.execute(series_stmt).all()
    series = []
    for r in series_rows:
        cents = int(getattr(r, "cents", 0) or (r[2] if isinstance(r, tuple) and len(r) > 2 else 0) or 0)
        series.append({
            "bucket": str(getattr(r, "bucket")),
            "count": int(getattr(r, "count", 0) or 0),
            "spend_usd": _fmt_usd(Decimal(cents) / Decimal(100)),
        })

    # Totals: count(*) and sum of per-row prices rounded to cents (HALF_UP)
    # Sum per-row cents using DB round to 0 decimals after multiplying by 100 (HALF_UP on Postgres; acceptable for positives)
    total_stmt = sa.select(
        sa.func.count().label("n"),
        sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("sum_cents")
    ).where(sa.and_(*where))
    total_row = db.execute(total_stmt).one_or_none()
    total_requests = int(getattr(total_row, "n", 0) if total_row else 0)
    # Fallback for tuple-like
    if total_requests == 0 and isinstance(total_row, tuple) and len(total_row) >= 1:
        try:
            total_requests = int(total_row[0] or 0)
        except Exception:
            total_requests = 0
    total_cents = int((getattr(total_row, "sum_cents", 0) if total_row else 0) or (total_row[1] if isinstance(total_row, tuple) and len(total_row) > 1 else 0) or 0)
    total_spend_usd = _fmt_usd(Decimal(total_cents) / Decimal(100))

    # By type
    by_type_rows = _spend_by_type(db, uid, dt_start, dt_end, include_tests=include_tests)
    by_type = {}
    for r in by_type_rows:
        name = str(getattr(r, "request_type"))
        cents = int(getattr(r, "cents", 0) or (r[1] if isinstance(r, tuple) and len(r) > 1 else 0) or 0)
        by_type[name] = {
            "count": int(getattr(r, "requests", 0) or 0),
            "spend_usd": _fmt_usd(Decimal(cents) / Decimal(100)),
        }

    # By model
    by_model_rows = _spend_by_model(db, uid, dt_start, dt_end, include_tests=include_tests)
    by_model = {}
    for r in by_model_rows:
        model = str(getattr(r, "model"))
        cents = int(getattr(r, "cents", 0) or (r[3] if isinstance(r, tuple) and len(r) > 3 else 0) or 0)
        by_model[model] = {
            "count": int(getattr(r, "requests", 0) or 0),
            "avg_price_usd": float(getattr(r, "avg_price_usd", 0) or 0),
            "spend_usd": _fmt_usd(Decimal(cents) / Decimal(100)),
        }

    # Multi-model usage distribution (by output_models count)
    mm_rows = _multi_model_counts(db, uid, dt_start, dt_end, include_tests=include_tests)
    # handle both aliased "model_count" or legacy "output_models" from the row
    multi_model = {}
    for r in mm_rows:
        try:
            raw = getattr(r, "model_count", None) if hasattr(r, "model_count") else getattr(r, "output_models", 0)
            k = int(0 if raw is None else raw)
        except Exception:
            # fallback attempt for tuple-like rows
            try:
                k = int(r[0])
            except Exception:
                k = 0
        multi_model[str(k)] = int(getattr(r, "n", 0) or (r[1] if isinstance(r, tuple) and len(r) > 1 else 0))

    # Token mix: sum prompt vs completion tokens (estimates)
    tok_stmt = sa.select(
        sa.func.sum(c.c.prompt_tokens).label("p"),
        sa.func.sum(c.c.completion_tokens).label("c"),
    ).where(sa.and_(*where))
    tok_row = db.execute(tok_stmt).one_or_none()
    token_mix = {
        "prompt": int(getattr(tok_row, "p", 0) or 0) if tok_row else 0,
        "completion": int(getattr(tok_row, "c", 0) or 0) if tok_row else 0,
    }

    # Requests by type over time (for stacked area)
    rbt_rows = _requests_by_type(db, uid, dt_start, dt_end, use_bucket, tz, include_tests=include_tests)
    requests_by_type = [
        {"bucket": str(getattr(r, "bucket")), "request_type": str(getattr(r, "request_type")), "count": int(getattr(r, "count", 0) or 0)}
        for r in rbt_rows
    ]

    # Latency: average jobs.latency_ms for related charges within filter
    try:
        lat_rows = _latency_series(
            db,
            uid,
            dt_start,
            dt_end,
            use_bucket,
            tz,
            include_tests=include_tests,
        )
        # Provide average across range and the series
        series_lat = [{"bucket": str(getattr(r, "bucket")), "avg_ms": float(getattr(r, "avg_ms", 0) or 0)} for r in lat_rows]
        avg_ms = float(sum(p["avg_ms"] for p in series_lat) / max(1, len(series_lat))) if series_lat else 0.0
        latency = {"avg_ms": avg_ms, "series": series_lat}
    except Exception:
        total_reqs = sum(p["count"] for p in series) or 1
        avg_prompt = token_mix["prompt"] / max(1, total_reqs)
        avg_completion = token_mix["completion"] / max(1, total_reqs)
        latency = {"avg_prompt_tokens": float(avg_prompt), "avg_completion_tokens": float(avg_completion)}

    # Balance timeline (ledger deltas over buckets)
    b_rows = _balance_series(
        db,
        uid,
        dt_start,
        dt_end,
        use_bucket,
        tz,
        include_tests=include_tests,
    )
    balance_series = [
        {
            "bucket": str(getattr(r, "bucket")),
            "delta_cents": int(getattr(r, "delta_cents", 0) or 0),
            "running_cents": int(getattr(r, "running_cents", 0) or 0),
            "deposits_cents": int(getattr(r, "deposits_cents", 0) or 0),
            "charges_cents": int(getattr(r, "charges_cents", 0) or 0),
        }
        for r in b_rows
    ]

    # Tokens by model (avg prompt/completion)
    tbm_rows = _tokens_by_model(db, uid, dt_start, dt_end, include_tests=include_tests)
    tokens_by_model = [
        {
            "model": str(getattr(r, "model")),
            "avg_prompt": float(getattr(r, "avg_prompt", 0) or 0),
            "avg_completion": float(getattr(r, "avg_completion", 0) or 0),
        }
        for r in tbm_rows
    ]

    # Recent ledger
    # Clamp recent ledger limit to max 200
    eff_recent_limit = min(int(recent_limit or 50), 200)
    rl_rows = _recent_ledger(db, uid, dt_start, dt_end, limit=eff_recent_limit)
    recent_ledger = [
        {
            "id": str(getattr(r, "id")),
            "created_at": str(getattr(r, "created_at")),
            "delta_cents": int(getattr(r, "delta_cents", 0) or 0),
            "type": str(getattr(r, "type", "") or ""),
        }
        for r in rl_rows
    ]

    # Current balance (fresh from DB rows; not cached/anchored)
    current_balance_cents, balance_usd = _fresh_current_balance(db, uid, include_tests=include_tests)

    # Do not shift historical series to current balance; return true running balances for bucket boundaries.

    # Avg price (rolling recent 100 charges); fallback to series avg if empty
    try:
        recent_filters = [c.c.user_id == uid]
        if not include_tests:
            recent_filters.append(c.c.is_test == sa.false())
        recent_sub = sa.select(_price_expr.label("price")).where(
            sa.and_(*recent_filters)
        ).order_by(c.c.created_at.desc()).limit(100).subquery()
        avg_row = db.execute(sa.select(sa.func.avg(recent_sub.c.price))).one_or_none()
        avg_recent = getattr(avg_row, "avg_1", None) if avg_row is not None else None
        # SQLAlchemy may alias avg field differently across dialects; fetch scalar sensibly
        if isinstance(avg_row, tuple) and len(avg_row) >= 1 and avg_recent is None:
            avg_recent = avg_row[0]
        avg_price_recent_usd = _fmt_usd(avg_recent or 0)
        if (avg_recent is None) or (Decimal(str(avg_recent or 0)) == Decimal("0")):
            # fallback to series totals if present
            total_count = sum(int(p.get("count", 0) or 0) for p in series)
            total_spend = sum(Decimal(p.get("spend_usd", "0") or "0") for p in series)
            avg_fallback = (total_spend / Decimal(total_count)) if total_count > 0 else Decimal("0")
            avg_price_recent_usd = _fmt_usd(avg_fallback)
    except Exception:
        avg_price_recent_usd = _fmt_usd(0)

    resp = {
        "series": series,
    "requests_by_type": requests_by_type,
        "by_type": by_type,
        "by_model": by_model,
        "multi_model": multi_model,
        "token_mix": token_mix,
        "latency": latency,
        "balance_timeline": balance_series,
    "tokens_by_model": tokens_by_model,
    "recent_ledger": recent_ledger,
    "current_balance_cents": current_balance_cents,
    "balance_usd": balance_usd,
    "avg_price_recent_usd": avg_price_recent_usd,
    "totals": { "requests": total_requests, "spend_usd": total_spend_usd },
    }
    # Store in cache (note: current balance fields will be overridden on retrieval to avoid staleness)
    try:
        with _summary_cache_lock:
            _summary_cache[cache_key] = (now_ts, resp)
    except Exception:
        pass
    return resp


# --- CSV Export Removed -------------------------------------------------------
# The /analytics/export.csv endpoint has been removed to enforce analytics layer
# as the single source of truth for downstream consumption.
# 
# For raw data access, use the analytics schema materialized views via the
# analytics_reader database role. See docs/ANALYTICS_SOURCE_CONTRACT.md for details.
# ------------------------------------------------------------------------------


# --- Jobs lifecycle analytics -------------------------------------------------

@analytics_router.get("/jobs")
async def jobs_analytics(
    db: Annotated[Session, Depends(get_db)],
    current_user=Depends(auth_dep.get_current_user),
    # Optional range and bucketing for time series
    start: Optional[str] = Query(default=None, alias="from", description="ISO start (inclusive)"),
    end: Optional[str] = Query(default=None, alias="to", description="ISO end (exclusive)"),
    bucket: Optional[str] = Query(default=None, description="hour|day|week|month (auto if omitted)"),
    tz: Optional[str] = Query(default=None, description="IANA tz name for bucketing (closures_over_time, snapshots_over_time)"),
):
    """Return simple lifecycle analytics for jobs.

    Fields:
    - counts_by_stage_active: counts by latest application stage for active (not archived, not deleted)
    - hired_count: count of jobs where stage == 'hired' (any state)
    - closed_count: count of jobs where is_archived = true and stage != 'hired'
    - closures_over_time: weekly counts grouped by deleted_at (soft deletes)
    - funnel_active: canonical stage order [applied, interviewing, offer, hired]
    - snapshots_over_time: time series of analytics snapshot rows grouped by bucket with fields { bucket, snapshots, applied }
    """
    from restailor.models import Job  # local import to avoid circulars

    j = Job.__table__
    uid = int(getattr(current_user, "id", 0))

    # Parse range for time series (default last 30d if omitted)
    dt_start, dt_end, auto_bucket = _parse_range(start, end, tz)
    use_bucket = (bucket or auto_bucket).lower()

    _ensure_snapshot_state_fresh(db, uid)

    # 1) Active stage counts (exclude archived and deleted)
    state_tbl = AnalyticsJobSnapshotState.__table__
    stage_expr = _snapshot_stage_expr(state_tbl)
    rows = db.execute(
        sa.select(
            stage_expr.label("stage"),
            sa.func.count().label("n"),
        )
        .where(
            sa.and_(
                state_tbl.c.user_id == uid,
                state_tbl.c.is_active.is_(True),
            )
        )
        .group_by(stage_expr)
    ).all()
    counts_by_stage_active: dict[str, int] = {}
    for r in rows:
        stg = str(getattr(r, "stage", "") or "")
        stg_norm = stg.strip().lower() or "applied"
        if not stg:
            # Skip unknown/empty stage; UI funnels focus on known labels
            stg_norm = "applied"
        counts_by_stage_active[stg_norm] = int(getattr(r, "n", 0) or 0)

    # 2) hired_count (any state)
    hired_count_row = db.execute(
        sa.select(sa.func.count())
        .where(
            sa.and_(
                state_tbl.c.user_id == uid,
                state_tbl.c.is_hired.is_(True),
            )
        )
    ).one_or_none()
    try:
        hired_count = int(hired_count_row[0]) if isinstance(hired_count_row, tuple) else int(getattr(hired_count_row, "count_1", 0) or 0)
    except Exception:
        hired_count = int(getattr(hired_count_row, "count_1", 0) or 0) if hired_count_row else 0

    # 3) closed_count: archived and not hired
    closed_row = db.execute(
        sa.select(sa.func.count())
        .where(
            sa.and_(
                state_tbl.c.user_id == uid,
                state_tbl.c.is_active.is_(False),
                state_tbl.c.is_hired.is_(False),
            )
        )
    ).one_or_none()
    try:
        closed_count = int(closed_row[0]) if isinstance(closed_row, tuple) else int(getattr(closed_row, "count_1", 0) or 0)
    except Exception:
        closed_count = int(getattr(closed_row, "count_1", 0) or 0) if closed_row else 0

    # 4) closures_over_time: weekly groups by deleted_at
    try:
        dialect_name = getattr(getattr(db.bind, "dialect", None), "name", None) if getattr(db, "bind", None) else None
    except Exception:
        dialect_name = None
    bkt = _bucket_expr(j.c.deleted_at, "week", dialect_name, tz).label("bucket")
    closures_rows = db.execute(
        sa.select(bkt, sa.func.count().label("n"))
        .where(sa.and_(j.c.user_id == uid, j.c.deleted_at.is_not(None)))
        .group_by(bkt)
        .order_by(sa.text("bucket ASC"))
    ).all()
    closures_over_time = [
        {"bucket": str(getattr(r, "bucket")), "count": int(getattr(r, "n", 0) or 0)} for r in closures_rows
    ]

    # 5) funnel_active canonical order
    funnel_active = ["applied", "interviewing", "offer", "hired"]

    # 6) snapshots_over_time from analytics snapshot state (per-application rows already filtered)
    state_tbl = AnalyticsJobSnapshotState.__table__
    state_bucket_snap = _bucket_expr(state_tbl.c.created_at, use_bucket, dialect_name, tz).label("bucket")
    state_filters = sa.and_(
        state_tbl.c.user_id == uid,
        state_tbl.c.created_at >= dt_start,
        state_tbl.c.created_at < dt_end,
    state_tbl.c.is_active.is_(True),
    )
    snaps_stmt = sa.select(
        state_bucket_snap,
        sa.func.count().label("snapshots"),
    sa.func.sum(sa.case((state_tbl.c.is_applied.is_(True), 1), else_=0)).label("applied"),
    ).where(state_filters).group_by(state_bucket_snap).order_by(sa.text("bucket ASC"))
    snaps_rows = db.execute(snaps_stmt).all()
    snapshots_over_time = [
        {
            "bucket": str(getattr(r, "bucket")),
            "snapshots": int(getattr(r, "snapshots", 0) or (r[1] if isinstance(r, tuple) and len(r) > 1 else 0) or 0),
            "applied": int(getattr(r, "applied", 0) or (r[2] if isinstance(r, tuple) and len(r) > 2 else 0) or 0),
        }
        for r in snaps_rows
    ]

    # 7) stages_over_time (Interviewing, Offer, Hired) grouped by snapshot updated_at
    stage_bucket = _bucket_expr(state_tbl.c.updated_at, use_bucket, dialect_name, tz).label("bucket")
    stage_expr = _snapshot_stage_expr(state_tbl)
    stage_rows = db.execute(
        sa.select(
            stage_bucket,
            stage_expr.label("stage"),
            sa.func.count().label("n"),
        )
        .where(
            sa.and_(
                state_tbl.c.user_id == uid,
                state_tbl.c.updated_at >= dt_start,
                state_tbl.c.updated_at < dt_end,
                stage_expr.in_(["interviewing", "offer", "hired"]),
            )
        )
        .group_by(stage_bucket, stage_expr)
        .order_by(sa.text("bucket ASC"))
    ).all()
    # Pivot to { bucket, interviewing, offer, hired }
    stage_map: dict[str, dict[str, int]] = {}
    for r in stage_rows:
        b = str(getattr(r, "bucket"))
        st = str((getattr(r, "stage", "") or "")).lower()
        n = int(getattr(r, "n", 0) or 0)
        if st not in ("interviewing", "offer", "hired"):
            continue
        d = stage_map.setdefault(b, {"interviewing": 0, "offer": 0, "hired": 0})
        d[st] = n
    stages_over_time = [
        {"bucket": b, **vals} for b, vals in sorted(stage_map.items(), key=lambda kv: kv[0])
    ]

    # 8) cohort_over_time from analytics snapshot state (already joined to Job semantics)
    state_bucket_cohort = _bucket_expr(state_tbl.c.created_at, use_bucket, dialect_name, tz).label("bucket")
    cohort_stmt = sa.select(
        state_bucket_cohort,
        sa.func.count().label("snapshots"),
    sa.func.sum(sa.case((state_tbl.c.is_applied.is_(True), 1), else_=0)).label("applied"),
    sa.func.sum(sa.case((state_tbl.c.is_interviewing.is_(True), 1), else_=0)).label("interviewing"),
    sa.func.sum(sa.case((state_tbl.c.is_offer.is_(True), 1), else_=0)).label("offer"),
    sa.func.sum(sa.case((state_tbl.c.is_hired.is_(True), 1), else_=0)).label("hired"),
    ).where(state_filters).group_by(state_bucket_cohort).order_by(sa.text("bucket ASC"))
    cohort_rows = db.execute(cohort_stmt).all()
    cohort_over_time = [
        {
            "bucket": str(getattr(r, "bucket")),
            "snapshots": int(getattr(r, "snapshots", 0) or 0),
            "applied": int(getattr(r, "applied", 0) or 0),
            "interviewing": int(getattr(r, "interviewing", 0) or 0),
            "offer": int(getattr(r, "offer", 0) or 0),
            "hired": int(getattr(r, "hired", 0) or 0),
        }
        for r in cohort_rows
    ]

    return {
        "counts_by_stage_active": counts_by_stage_active,
        "hired_count": hired_count,
        "closed_count": closed_count,
        "closures_over_time": closures_over_time,
        "funnel_active": funnel_active,
        "snapshots_over_time": snapshots_over_time,
        "stages_over_time": stages_over_time,
        "cohort_over_time": cohort_over_time,
    }
