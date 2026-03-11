"""
Admin Analytics Router

Admin-only endpoints for aggregated analytics across all users.
Provides metrics for:
- User growth and signups
- Request volume by type (fit/tailor/judge)
- Revenue and spend tracking
- System health and usage patterns
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any, Optional
import logging

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from restailor import auth as auth_dep
from restailor.db import SessionLocal
from restailor.models import User, Charge, CreditLedger, UserBalance

logger = logging.getLogger(__name__)

admin_analytics_router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])


# --- Helper: DB Session ---
async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _fmt_usd(d: Decimal | int | float | None) -> str:
    """Format a number as USD string"""
    try:
        dec = d if isinstance(d, Decimal) else Decimal(str(d or 0))
    except Exception:
        dec = Decimal("0")
    return str(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --- Response Models ---
class UserStatsResponse(BaseModel):
    """User statistics"""
    total_users: int
    signup_users: int  # Users who registered but have no CreditLedger entries
    trial_users: int  # Users who claimed trial (have signup_grant)
    paid_users: int  # Users who have purchases
    admin_users: int
    verified_users: int
    active_7d: int
    active_30d: int


class SignupTrendsResponse(BaseModel):
    """Signup trends over time"""
    bucket: str
    count: int


class RequestVolumeResponse(BaseModel):
    """Request volume by type"""
    request_type: str
    count: int
    total_spend_usd: str


class RevenueMetricsResponse(BaseModel):
    """Revenue and spend metrics"""
    total_deposits_cents: int
    total_deposits_usd: str
    total_spend_cents: int
    total_spend_usd: str
    average_deposits_per_user_cents: int
    average_deposits_per_user_usd: str


class ModelUsageResponse(BaseModel):
    """Model usage statistics"""
    model: str
    request_count: int
    total_spend_usd: str
    avg_price_usd: str


class UserDrilldownResponse(BaseModel):
    """User-level drilldown data"""
    user_email: str
    user_id: int
    request_count: int
    total_amount_usd: str  # Could be spend or deposits depending on metric
    last_activity: str | None
    account_type: str  # "trial", "paid", "admin"


class SystemHealthResponse(BaseModel):
    """System health metrics"""
    total_requests_24h: int
    total_spend_24h_usd: str
    avg_latency_ms: float | None
    error_rate: float


class OverviewResponse(BaseModel):
    """Admin analytics overview"""
    user_stats: UserStatsResponse
    revenue_metrics: RevenueMetricsResponse
    system_health: SystemHealthResponse


# --- Endpoints ---

@admin_analytics_router.get("/overview", response_model=OverviewResponse)
async def get_admin_overview(
    current_user: Annotated[User, Depends(auth_dep.require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Get admin analytics overview with key metrics.
    
    Requires admin role.
    """
    # User stats
    total_users = db.execute(
        sa.select(sa.func.count()).select_from(User).where(User.is_test == sa.false())
    ).scalar() or 0
    
    # Count signup users (no CreditLedger entries at all, excluding admins)
    signup_users_count = db.execute(
        sa.select(sa.func.count(sa.distinct(User.id)))
        .select_from(User)
        .outerjoin(CreditLedger, CreditLedger.user_id == User.id)
        .where(User.is_test == sa.false())
        .where(User.role != "admin")
        .where(CreditLedger.id == None)
    ).scalar() or 0
    
    # Count trial users (claimed trial via signup_grant, excluding admins and those who purchased)
    # First get users who have claimed trial
    users_with_trial = db.execute(
        sa.select(sa.func.array_agg(sa.distinct(CreditLedger.user_id)))
        .where(CreditLedger.note == "signup_grant")
    ).scalar() or []
    
    # Then exclude those who have made purchases
    users_with_purchases = db.execute(
        sa.select(sa.func.array_agg(sa.distinct(CreditLedger.user_id)))
        .where(CreditLedger.type == "purchase")
    ).scalar() or []
    
    # Trial users = have trial grant but no purchases, excluding admins
    trial_user_ids = set(users_with_trial or []) - set(users_with_purchases or [])
    
    if trial_user_ids:
        trial_users_count = db.execute(
            sa.select(sa.func.count())
            .select_from(User)
            .where(User.id.in_(trial_user_ids))
            .where(User.is_test == sa.false())
            .where(User.role != "admin")
        ).scalar() or 0
    else:
        trial_users_count = 0
    
    # Paid users (have purchases, excluding admins)
    paid_users_count = db.execute(
        sa.select(sa.func.count(sa.distinct(User.id)))
        .select_from(User)
        .join(CreditLedger, (CreditLedger.user_id == User.id) & (CreditLedger.type == "purchase"))
        .where(User.is_test == sa.false())
        .where(User.role != "admin")
    ).scalar() or 0
    
    admin_users = db.execute(
        sa.select(sa.func.count()).select_from(User).where(User.role == "admin").where(User.is_test == sa.false())
    ).scalar() or 0
    
    verified_users = db.execute(
        sa.select(sa.func.count()).select_from(User).where(User.is_verified == sa.true()).where(User.is_test == sa.false())
    ).scalar() or 0
    
    # Active users (made a request in last 7/30 days)
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    
    active_7d = db.execute(
        sa.select(sa.func.count(sa.distinct(Charge.user_id)))
        .select_from(Charge)
        .where(Charge.created_at >= seven_days_ago)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    ).scalar() or 0
    
    active_30d = db.execute(
        sa.select(sa.func.count(sa.distinct(Charge.user_id)))
        .select_from(Charge)
        .where(Charge.created_at >= thirty_days_ago)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    ).scalar() or 0
    
    user_stats = UserStatsResponse(
        total_users=int(total_users),
        signup_users=int(signup_users_count),
        trial_users=int(trial_users_count),
        paid_users=int(paid_users_count),
        admin_users=int(admin_users),
        verified_users=int(verified_users),
        active_7d=int(active_7d),
        active_30d=int(active_30d),
    )
    
    # Revenue metrics (deposits vs spend)
    total_deposits = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(CreditLedger.delta_cents), 0))
        .select_from(CreditLedger)
        .where(CreditLedger.type == "purchase")
        .where(CreditLedger.is_test == sa.false())
    ).scalar() or 0
    
    _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
    total_spend = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)), 0))
        .select_from(Charge)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    ).scalar() or 0
    
    avg_deposits = int(total_deposits) / max(1, int(total_users))
    
    revenue_metrics = RevenueMetricsResponse(
        total_deposits_cents=int(total_deposits),
        total_deposits_usd=_fmt_usd(int(total_deposits) / 100),
        total_spend_cents=int(total_spend),
        total_spend_usd=_fmt_usd(int(total_spend) / 100),
        average_deposits_per_user_cents=int(avg_deposits),
        average_deposits_per_user_usd=_fmt_usd(avg_deposits / 100),
    )
    
    # System health (last 24h)
    yesterday = now - timedelta(days=1)
    
    requests_24h = db.execute(
        sa.select(sa.func.count())
        .select_from(Charge)
        .where(Charge.created_at >= yesterday)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    ).scalar() or 0
    
    spend_24h = db.execute(
        sa.select(sa.func.coalesce(sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)), 0))
        .select_from(Charge)
        .where(Charge.created_at >= yesterday)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    ).scalar() or 0
    
    # Average latency from jobs (if available)
    try:
        from restailor.models import Job
        avg_latency_row = db.execute(
            sa.select(sa.func.avg(Job.latency_ms))
            .select_from(Job)
            .join(Charge, Charge.job_id == Job.id)
            .where(Charge.created_at >= yesterday)
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
        ).scalar()
        avg_latency = float(avg_latency_row) if avg_latency_row else None
    except Exception:
        avg_latency = None
    
    # Error rate (jobs with status='error')
    try:
        from restailor.models import Job
        total_jobs = db.execute(
            sa.select(sa.func.count())
            .select_from(Job)
            .join(Charge, Charge.job_id == Job.id)
            .where(Charge.created_at >= yesterday)
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
        ).scalar() or 0
        
        error_jobs = db.execute(
            sa.select(sa.func.count())
            .select_from(Job)
            .join(Charge, Charge.job_id == Job.id)
            .where(Charge.created_at >= yesterday)
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
            .where(Job.status == "error")
        ).scalar() or 0
        
        error_rate = (int(error_jobs) / max(1, int(total_jobs))) * 100
    except Exception:
        error_rate = 0.0
    
    system_health = SystemHealthResponse(
        total_requests_24h=int(requests_24h),
        total_spend_24h_usd=_fmt_usd(int(spend_24h) / 100),
        avg_latency_ms=avg_latency,
        error_rate=error_rate,
    )
    
    return OverviewResponse(
        user_stats=user_stats,
        revenue_metrics=revenue_metrics,
        system_health=system_health,
    )


@admin_analytics_router.get("/signups", response_model=list[SignupTrendsResponse])
async def get_signup_trends(
    current_user: Annotated[User, Depends(auth_dep.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Optional[int] = Query(default=None, ge=1, le=3650, description="Number of days to look back (omit for all-time)"),
    bucket: str = Query(default="day", regex="^(day|week|month)$", description="Time bucket: day, week, or month"),
):
    """
    Get signup trends over time.
    
    Returns signup counts grouped by time bucket.
    If days is omitted, returns all-time data.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days) if days else None
    
    # Determine bucket expression
    dialect_name = getattr(getattr(db.bind, "dialect", None), "name", None) if getattr(db, "bind", None) else None
    if (dialect_name or "").lower().startswith("sqlite"):
        # SQLite fallback
        if bucket == "week":
            bucket_expr = sa.func.date(sa.func.strftime("%Y-%m-%d", User.created_at), "weekday 1")
        elif bucket == "month":
            bucket_expr = sa.func.strftime("%Y-%m-01", User.created_at)
        else:  # day
            bucket_expr = sa.func.strftime("%Y-%m-%d", User.created_at)
    else:
        # PostgreSQL
        bucket_expr = sa.func.date_trunc(bucket, User.created_at)
    
    # Build query with optional date filter
    query = (
        sa.select(
            bucket_expr.label("bucket"),
            sa.func.count().label("count"),
        )
        .select_from(User)
        .where(User.is_test == sa.false())
    )
    
    if start:
        query = query.where(User.created_at >= start)
    
    query = query.group_by(bucket_expr).order_by(sa.text("bucket ASC"))
    
    rows = db.execute(query).all()
    
    return [
        SignupTrendsResponse(bucket=str(r.bucket), count=int(r.count))
        for r in rows
    ]


@admin_analytics_router.get("/requests", response_model=list[RequestVolumeResponse])
async def get_request_volume(
    current_user: Annotated[User, Depends(auth_dep.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Optional[int] = Query(default=None, ge=1, le=3650, description="Number of days to look back (omit for all-time)"),
):
    """
    Get request volume by type (fit/tailor/judge).
    
    Returns total counts and spend for each request type.
    Counts ALL successful requests (single and multi-model) - excludes only test data and failed requests.
    If days is omitted, returns all-time data.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days) if days else None
    
    _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
    
    query = (
        sa.select(
            Charge.request_type,
            sa.func.count().label("count"),
            sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("spend_cents"),
        )
        .select_from(Charge)
        .where(Charge.is_test == sa.false())
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    )
    
    if start:
        query = query.where(Charge.created_at >= start)
    
    query = query.group_by(Charge.request_type)
    
    rows = db.execute(query).all()
    
    return [
        RequestVolumeResponse(
            request_type=str(r.request_type),
            count=int(r.count),
            total_spend_usd=_fmt_usd((int(r.spend_cents or 0)) / 100),
        )
        for r in rows
    ]


@admin_analytics_router.get("/models", response_model=list[ModelUsageResponse])
async def get_model_usage(
    current_user: Annotated[User, Depends(auth_dep.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Optional[int] = Query(default=None, ge=1, le=3650, description="Number of days to look back (omit for all-time)"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of top models to return"),
):
    """
    Get model usage statistics.
    
    Returns top models by request count with spend metrics.
    If days is omitted, returns all-time data.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days) if days else None
    
    _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
    
    query = (
        sa.select(
            Charge.model,
            sa.func.count().label("count"),
            sa.func.avg(_price_expr).label("avg_price"),
            sa.func.sum(sa.func.round(_price_expr * sa.literal(100), 0)).label("spend_cents"),
        )
        .select_from(Charge)
        .where(Charge.is_test == sa.false())
        .where(Charge.model != None)
        .where(Charge.prompt_tokens > 0)
        .where(Charge.completion_tokens > 0)
    )
    
    if start:
        query = query.where(Charge.created_at >= start)
    
    query = query.group_by(Charge.model).order_by(sa.text("count DESC")).limit(limit)
    
    rows = db.execute(query).all()
    
    return [
        ModelUsageResponse(
            model=str(r.model),
            request_count=int(r.count),
            total_spend_usd=_fmt_usd((int(r.spend_cents or 0)) / 100),
            avg_price_usd=_fmt_usd(float(r.avg_price or 0)),
        )
        for r in rows
    ]


@admin_analytics_router.get("/drilldown/users", response_model=list[UserDrilldownResponse])
async def get_user_drilldown(
    current_user: Annotated[User, Depends(auth_dep.require_admin)],
    db: Annotated[Session, Depends(get_db)],
    days: Optional[int] = Query(default=None, ge=1, le=3650, description="Number of days to look back (omit for all-time)"),
    metric: str = Query(default="requests", regex="^(requests|spend|active|deposits|balance|users)$", description="Metric to break down by user"),
    request_type: Optional[str] = Query(default=None, description="Filter by request type (judge, tailor, fit, etc.)"),
    model: Optional[str] = Query(default=None, description="Filter by model name"),
    account_type: Optional[str] = Query(default=None, regex="^(signup|trial|paid|verified)$", description="Filter by account type"),
    signup_date: Optional[str] = Query(default=None, description="Filter by signup date (YYYY-MM-DD)"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of users to return"),
):
    """
    Get user-level drilldown data for a specific metric.
    
    Allows drilling into aggregate metrics to see individual user contributions.
    Supports filtering by request_type, model, and account_type.
    
    Metrics:
    - requests: Users by request count
    - spend: Users by total spend (API usage costs from Charge table)
    - deposits: Users by total deposits (purchases from CreditLedger table)
    - balance: Users by net balance (deposits - spend)
    - active: Recently active users (users with charges, ordered by last activity)
    - users: All users (regardless of activity, ordered by signup date)
    """
    # Debug logging
    print(f"[DEBUG] get_user_drilldown called: metric={metric}, days={days}, request_type={request_type}, model={model}, account_type={account_type}, signup_date={signup_date}")
    
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days) if days else None
    
    # Determine account type for each user
    # Subquery to check if user has made purchases
    has_purchase_subq = (
        sa.select(sa.func.count(CreditLedger.id))
        .where(
            (CreditLedger.user_id == User.id) & 
            (CreditLedger.type == "purchase")
        )
        .correlate(User)
        .scalar_subquery()
    )
    
    # Subquery to check if user has claimed trial (signup_grant)
    has_trial_subq = (
        sa.select(sa.func.count(CreditLedger.id))
        .where(
            (CreditLedger.user_id == User.id) & 
            (CreditLedger.note == "signup_grant")
        )
        .correlate(User)
        .scalar_subquery()
    )
    
    # Subquery to check if user has any CreditLedger entries
    has_any_ledger_subq = (
        sa.select(sa.func.count(CreditLedger.id))
        .where(CreditLedger.user_id == User.id)
        .correlate(User)
        .scalar_subquery()
    )
    
    account_type_expr = sa.case(
        (User.role == "admin", "admin"),
        (has_purchase_subq > 0, "paid"),
        (has_trial_subq > 0, "trial"),
        (has_any_ledger_subq == 0, "signup"),
        else_="signup"  # fallback
    )
    
    # Build additional WHERE clauses for account_type filtering
    account_type_where = []
    if account_type == "signup":
        account_type_where.append((User.role != "admin") & (has_any_ledger_subq == 0))
    elif account_type == "trial":
        account_type_where.append((User.role != "admin") & (has_trial_subq > 0) & (has_purchase_subq == 0))
    elif account_type == "paid":
        account_type_where.append((User.role != "admin") & (has_purchase_subq > 0))
    elif account_type == "verified":
        account_type_where.append(User.is_email_verified == sa.true())
    
    if metric == "requests":
        # Break down by request count
        _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
        
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.count(Charge.id).label("request_count"),
                sa.func.sum(
                    sa.cast(_price_expr * 100, sa.Integer)
                ).label("amount_cents"),  # Total spend (API usage costs from Charge table)
                sa.func.max(Charge.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .join(Charge, Charge.user_id == User.id)
            .where(User.is_test == sa.false())
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
        )
        
        if start:
            query = query.where(Charge.created_at >= start)
        
        if request_type:
            query = query.where(Charge.request_type == request_type)
        
        if model:
            query = query.where(Charge.model == model)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            # Filter by signup date (created_at on the same day)
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass  # Skip invalid dates
        
        query = (
            query.group_by(User.id, User.username, account_type_expr)
            .order_by(sa.text("request_count DESC"))
            .limit(limit)
        )
        
    elif metric == "spend":
        # Break down by total spend (API usage costs from Charge table)
        _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
        
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.count(Charge.id).label("request_count"),
                sa.func.sum(
                    sa.cast(_price_expr * 100, sa.Integer)
                ).label("amount_cents"),  # Total spend (API usage costs)
                sa.func.max(Charge.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .join(Charge, Charge.user_id == User.id)
            .where(User.is_test == sa.false())
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
        )
        
        if start:
            query = query.where(Charge.created_at >= start)
        
        if request_type:
            query = query.where(Charge.request_type == request_type)
        
        if model:
            query = query.where(Charge.model == model)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            # Filter by signup date (created_at on the same day)
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass  # Skip invalid dates
        
        query = (
            query.group_by(User.id, User.username, account_type_expr)
            .order_by(sa.text("amount_cents DESC"))
            .limit(limit)
        )
    
    elif metric == "active":
        # Recently active users
        _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
        
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.count(Charge.id).label("request_count"),
                sa.func.sum(
                    sa.cast(_price_expr * 100, sa.Integer)
                ).label("amount_cents"),  # Total spend (API usage costs from Charge table)
                sa.func.max(Charge.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .join(Charge, Charge.user_id == User.id)
            .where(User.is_test == sa.false())
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
        )
        
        if start:
            query = query.where(Charge.created_at >= start)
        
        if request_type:
            query = query.where(Charge.request_type == request_type)
        
        if model:
            query = query.where(Charge.model == model)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            # Filter by signup date (created_at on the same day)
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass  # Skip invalid dates
        
        query = (
            query.group_by(User.id, User.username, account_type_expr)
            .order_by(sa.text("last_activity DESC"))
            .limit(limit)
        )
    
    elif metric == "deposits":
        # Break down by total deposits (purchases from CreditLedger)
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.count(CreditLedger.id).label("request_count"),  # Count of purchases
                sa.func.sum(CreditLedger.delta_cents).label("amount_cents"),  # Sum of deposits
                sa.func.max(CreditLedger.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .join(CreditLedger, CreditLedger.user_id == User.id)
            .where(User.is_test == sa.false())
            .where(CreditLedger.type == "purchase")
        )
        
        if start:
            query = query.where(CreditLedger.created_at >= start)
        
        # Note: request_type and model filters don't apply to deposits (CreditLedger doesn't have these fields)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            # Filter by signup date (created_at on the same day)
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass  # Skip invalid dates
        
        query = (
            query.group_by(User.id, User.username, account_type_expr)
            .order_by(sa.text("amount_cents DESC"))
            .limit(limit)
        )
    
    elif metric == "balance":
        # Break down by net balance (deposits - spend)
        _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
        
        # Subquery for total deposits per user
        deposits_subq = (
            sa.select(
                CreditLedger.user_id,
                sa.func.coalesce(sa.func.sum(CreditLedger.delta_cents), 0).label("deposit_cents")
            )
            .where(CreditLedger.type == "purchase")
            .group_by(CreditLedger.user_id)
            .subquery()
        )
        
        # Subquery for total spend per user
        spend_subq = (
            sa.select(
                Charge.user_id,
                sa.func.coalesce(sa.func.sum(sa.cast(_price_expr * 100, sa.Integer)), 0).label("spend_cents")
            )
            .where(Charge.is_test == sa.false())
            .where(Charge.prompt_tokens > 0)
            .where(Charge.completion_tokens > 0)
            .group_by(Charge.user_id)
            .subquery()
        )
        
        # Main query joining both subqueries
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.coalesce(sa.func.count(sa.distinct(Charge.id)), 0).label("request_count"),  # Count of all requests
                (sa.func.coalesce(deposits_subq.c.deposit_cents, 0) - sa.func.coalesce(spend_subq.c.spend_cents, 0)).label("amount_cents"),  # Net balance
                sa.func.max(Charge.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .outerjoin(deposits_subq, deposits_subq.c.user_id == User.id)
            .outerjoin(spend_subq, spend_subq.c.user_id == User.id)
            .outerjoin(Charge, Charge.user_id == User.id)
            .where(User.is_test == sa.false())
            .where(
                sa.or_(
                    deposits_subq.c.deposit_cents.isnot(None),
                    spend_subq.c.spend_cents.isnot(None)
                )
            )
        )
        
        # Note: For balance, we show all users who have either deposits or charges
        # Time filtering doesn't apply to balance (it's cumulative)
        # request_type and model filters don't apply to balance (it's aggregate)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass
        
        query = (
            query.group_by(User.id, User.username, account_type_expr, deposits_subq.c.deposit_cents, spend_subq.c.spend_cents)
            .order_by(sa.text("amount_cents DESC"))
            .limit(limit)
        )
    
    elif metric == "users":
        # All users (regardless of activity)
        _price_expr = sa.func.coalesce(Charge.price_to_user_usd_real, Charge.price_to_user_usd)
        
        query = (
            sa.select(
                User.username.label("user_email"),
                User.id.label("user_id"),
                sa.func.coalesce(sa.func.count(Charge.id), 0).label("request_count"),
                sa.func.coalesce(sa.func.sum(
                    sa.cast(_price_expr * 100, sa.Integer)
                ), 0).label("amount_cents"),  # Total spend (API usage costs)
                sa.func.max(Charge.created_at).label("last_activity"),
                account_type_expr.label("account_type"),
            )
            .select_from(User)
            .outerjoin(Charge, (Charge.user_id == User.id) & (Charge.is_test == sa.false()) & (Charge.prompt_tokens > 0) & (Charge.completion_tokens > 0))
            .where(User.is_test == sa.false())
        )
        
        # Time filtering for users metric shows users who signed up in that timeframe
        if start:
            query = query.where(User.created_at >= start)
        
        # Note: request_type and model filters don't apply to users metric (shows all users)
        
        if account_type_where:
            query = query.where(sa.and_(*account_type_where))
        
        if signup_date:
            try:
                signup_dt = datetime.fromisoformat(signup_date).replace(tzinfo=timezone.utc)
                next_day = signup_dt + timedelta(days=1)
                query = query.where(User.created_at >= signup_dt).where(User.created_at < next_day)
            except (ValueError, TypeError):
                pass
        
        query = (
            query.group_by(User.id, User.username, account_type_expr)
            .order_by(User.created_at.desc())  # Order by signup date (newest first)
            .limit(limit)
        )
    
    else:
        # Should never reach here due to regex validation, but handle gracefully
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}")
    
    rows = db.execute(query).all()
    
    return [
        UserDrilldownResponse(
            user_email=str(r.user_email),
            user_id=int(r.user_id),
            request_count=int(r.request_count),
            total_amount_usd=_fmt_usd((int(r.amount_cents or 0)) / 100),
            last_activity=r.last_activity.isoformat() if r.last_activity else None,
            account_type=str(r.account_type),
        )
        for r in rows
    ]
