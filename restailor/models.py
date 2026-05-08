from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, Text, Float, Integer, Index, LargeBinary, ForeignKey, DateTime, Boolean, Numeric, BigInteger
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from decimal import Decimal


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(length=150), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(length=255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Email verification flag
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    # Email checks
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    email_verification_token: Mapped[str | None] = mapped_column(String(length=128), nullable=True, index=True)
    browser_fingerprint: Mapped[str | None] = mapped_column(String(length=128), nullable=True, index=True)
    # Account credits (for free usage grants)
    credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # User profile & data retention preferences
    public_profile: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    dont_save_future_data: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
    )
    # Role for access control: 'user' or 'admin'
    role: Mapped[str] = mapped_column(String(length=20), nullable=False, default="user", server_default="user")
    # Soft-deletion and forfeiture timestamps
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credits_forfeited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Track which snapshot user is currently viewing (for SSR reload on refresh)
    current_snapshot_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship to jobs
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    # Relationship to test checkbox (for testing checkbox persistence)
    test_checkbox: Mapped["TestCheckbox | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    # Timestamps (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        server_onupdate=sa.text("now()"),
        index=True,
    )
    # --- 2FA / TOTP columns (managed primarily via raw SQL in twofa_repo) ---
    # These were added via migrations; we map them here so sqlite test DBs created via ORM have them.
    two_factor_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False, server_default=sa.text("false"))
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_2fa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
    )


class UserProviderKey(Base):
    __tablename__ = "user_provider_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(length=32), nullable=False)
    key_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_tail: Mapped[str] = mapped_column(String(length=16), nullable=False)
    storage_mode: Mapped[str] = mapped_column(String(length=32), nullable=False, default="server", server_default="server")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "provider", name="uq_user_provider_keys_user_provider"),
        Index("ix_user_provider_keys_user_provider", "user_id", "provider"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(String(length=50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        server_onupdate=sa.text("now()"),
    )
    input_hash: Mapped[str] = mapped_column(String(length=128), nullable=False)
    # Flow indicator (non-PII)
    job_flow: Mapped[str | None] = mapped_column(String(length=20), nullable=True, index=True)
    # Source page/context (non-PII), e.g., "Resume Tailor", "Model Benchmark"
    source_page: Mapped[str | None] = mapped_column(String(length=50), nullable=True, index=True)
    # Encrypted input (resume only)
    resume_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Encrypted job description (JD)
    jd_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Encrypted candidate text (for judge-only flow)
    candidate_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Job-level metrics
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Per-job access token for ownership/authZ (capability secret)
    access_token: Mapped[str] = mapped_column(String(length=128), nullable=False, index=True)
    # Client identifier (from X-Client-Id header or derived), used for concurrency limits
    client_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True, index=True)
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)

    # UI management flags (do not affect processing lifecycle)
    # is_staged: Marks a job/result as staged (e.g., user wants to keep it handy/pinned in UI)
    # is_archived: Soft-hide from default views without deleting data
    is_staged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    staged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft-delete timestamp (legacy history UI)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Per-job stage tracking (mirrors application state for analytics/history views)
    stage: Mapped[str | None] = mapped_column(String(length=20), nullable=True, index=True)
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    is_interviewing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    is_offer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    is_hired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)

    # Owner (authenticated user)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user: Mapped[User | None] = relationship(back_populates="jobs")

    # Relationship to outputs
    outputs: Mapped[list["JobOutput"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    # Analytics fields removed (were unused): request_group_id, output_models, input_models

    __table_args__ = (
        Index("ix_jobs_input_hash", "input_hash"),
    )


class JobOutput(Base):
    __tablename__ = "job_outputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    # 'tailored' | 'judge' | 'fit' | maybe 'error' in the future
    type: Mapped[str] = mapped_column(String(length=20), nullable=False, index=True)
    # Encrypted output content
    content_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()")
    )
    # Optional per-output metrics
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    job: Mapped[Job] = relationship(back_populates="outputs")

    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)


    # NOTE (clarified): A JobOutput row with type='charge' is an auxiliary audit marker created at
    # job creation time (early observability). The authoritative billing ledger is the `charges`
    # table written via services.postprocess.record_charge_for_job. Do not treat JobOutput(type='charge')
    # as a replacement for the charges table; reconcile missing Charge rows by comparing jobs having
    # this marker but lacking a corresponding `charges` entry.


class Charge(Base):
    __tablename__ = "charges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()")
    )
    # Match users.id type (Integer) and jobs.id type (UUID)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    # Number of output models actually invoked for this charge
    output_models: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Number of upstream input models whose outputs fed into this request (e.g. judge reading N tailor outputs)
    input_models: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Provider-reported real token counts (nullable; populated progressively)
    prompt_tokens_real: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens_real: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # How the (prompt_tokens, completion_tokens) estimates were derived (e.g., 'heuristic_v1', 'provider_usage')
    token_estimation_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Percentage error vs real when both known: ((est-real)/real)*100 rounded
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    price_to_user_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    # Real cost figures when billing from provider real tokens; nullable for legacy/estimated-only rows
    cost_usd_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    price_to_user_usd_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD", server_default=sa.text("'USD'"))
    pricing_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    # Flag when only partial real token data (one side) was available at charge time (analytics only)
    is_partial_real_tokens: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)
    multiplier_used: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    __table_args__ = (
        Index("ix_charges_req_model_created_at", "request_type", "model", sa.text("created_at DESC")),
        Index("ix_charges_user_created_at", "user_id", sa.text("created_at DESC")),
    )


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    delta_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional admin user who performed the ledger action
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_credit_ledger_user_created_at", "user_id", sa.text("created_at DESC")),
    Index("ix_credit_ledger_provider_ref", "provider_ref"),
        Index("ix_credit_ledger_admin_created_at", "admin_id", sa.text("created_at DESC")),
    )
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)


class UserBalance(Base):
    __tablename__ = "user_balance"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()")
    )
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        index=True,
    )
    # Optional FK to users for correlation; keep nullable to log events without a user row
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    # kind: 'verify' | 'reset' | 'other'
    kind: Mapped[str] = mapped_column(String(length=20), nullable=False, default="other", server_default="other", index=True)
    # source: which endpoint or flow initiated the send
    source: Mapped[str | None] = mapped_column(String(length=64), nullable=True, index=True)
    # status: 'sent' | 'skipped' | 'error'
    status: Mapped[str] = mapped_column(String(length=16), nullable=False, default="sent", server_default="sent", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # request context (best-effort, not PII heavy)
    client_id: Mapped[str | None] = mapped_column(String(length=64), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    __table_args__ = (
        Index("ix_email_logs_created_desc", sa.text("created_at DESC")),
        Index("ix_email_logs_recipient", "recipient"),
    )
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        index=True,
    )
    # Nullable FK to users for correlation; do not cascade deletes to preserve audit trail
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="info", server_default="info", index=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Flag rows created by tests/e2e/demo for safe cleanup (optional)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)

    __table_args__ = (
        Index("ix_audit_events_type_created", "event_type", sa.text("created_at DESC")),
    )


class Application(Base):
    """Represents a single applied job snapshot per (user, jd_hash, base_hash).

    Stores encrypted JSON snapshot of the tailored resume/application output. Enforces
    uniqueness via an `applied_key` compound key of the form `${user_id}:${jd_hash}:${base_hash}`.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    base_hash: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # `${user_id}:${jd_hash}:${base_hash}` for fast idempotent upsert
    applied_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_input_hashes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sa.text("'[]'::jsonb"),
    )
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    jd_text_norm: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Encrypted JSON snapshot (pgp_sym_encrypt output)
    snapshot_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # boolean flag replacing prior 'kind' column
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text('false'), index=True)
    is_interviewing: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        index=True,
    )
    is_offer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        index=True,
    )
    is_hired: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa.text("false"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        server_onupdate=sa.text("now()"),
        index=True,
    )
    # Flag rows created by tests/e2e/demo for safe cleanup
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "jd_hash", name="uq_applications_user_jd"),
        Index("ix_applications_user_jd_base", "user_id", "jd_hash", "base_hash"),
        Index(
            "ix_applications_job_id_not_null_unique",
            "job_id",
            unique=True,
            postgresql_where=sa.text("job_id IS NOT NULL"),
        ),
        Index(
            "ix_applications_jd_text_norm",
            "jd_text_norm",
            postgresql_using="gin",
            postgresql_ops={"jd_text_norm": "gin_trgm_ops"},
        ),
    )

    @staticmethod
    def make_applied_key(user_id: int, jd_hash: str, base_hash: str) -> str:
        return f"{user_id}:{jd_hash}:{base_hash}"

    @staticmethod
    def make_job_applied_key(base_key: str, job_id: uuid.UUID | str | None) -> str:
        if job_id is None:
            return base_key
        return f"{base_key}#job:{job_id}"

    @classmethod
    def upsert(cls, session, *, user_id: int, jd_hash: str, base_hash: str, snapshot_enc: bytes,
               company: str | None = None, role: str | None = None, jd_url: str | None = None,
               jd_snippet: str | None = None, jd_text_norm: str | None = None,
         is_test: bool = False, is_applied: bool = False,
         job_id: uuid.UUID | None = None,
         job_input_hashes: list[str] | None = None) -> "Application":
        """Insert or update the application snapshot idempotently.

        Ensures a single row per (user_id, jd_hash) while still tracking the latest base hash.
        """
        from sqlalchemy.dialects.postgresql import insert

        applied_key = cls.make_applied_key(user_id, jd_hash, base_hash)
        insert_values = dict(
            user_id=user_id,
            jd_hash=jd_hash,
            base_hash=base_hash,
            applied_key=applied_key,
            snapshot_enc=snapshot_enc,
            company=company,
            role=role,
            jd_url=jd_url,
            jd_snippet=jd_snippet,
            jd_text_norm=jd_text_norm,
            is_test=is_test,
            is_applied=is_applied,
            job_id=job_id,
            job_input_hashes=list(job_input_hashes or []),
        )
        update_values: dict[str, Any] = {
            "snapshot_enc": snapshot_enc,
            "company": company,
            "role": role,
            "jd_url": jd_url,
            "updated_at": sa.text("now()"),
            "is_test": is_test,
            "is_applied": is_applied,
            "base_hash": base_hash,
            "applied_key": applied_key,
        }
        if jd_snippet is not None:
            update_values["jd_snippet"] = jd_snippet
        if jd_text_norm is not None:
            update_values["jd_text_norm"] = jd_text_norm
        if job_id is not None:
            update_values["job_id"] = job_id
        if job_input_hashes is not None:
            update_values["job_input_hashes"] = list(job_input_hashes)
        conflict_kwargs: dict[str, Any] = {"index_elements": [cls.user_id, cls.jd_hash]}

        stmt = (
            insert(cls)
            .values(**insert_values)
            .on_conflict_do_update(
                set_=update_values,
                **conflict_kwargs,
            )
            .returning(cls)
        )
        res = session.execute(stmt).scalar_one()
        return res

    @classmethod
    def get_by_key(cls, session, applied_key: str) -> "Application | None":
        return session.query(cls).filter_by(applied_key=applied_key).one_or_none()

    @classmethod
    def get(cls, session, *, user_id: int, jd_hash: str, base_hash: str) -> "Application | None":
        return cls.get_by_key(session, cls.make_applied_key(user_id, jd_hash, base_hash))


class AnalyticsJobSnapshotState(Base):
    __tablename__ = "analytics_job_snapshot_state"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        server_onupdate=sa.text("now()"),
    )
    is_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=sa.text("true"))
    is_interviewing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    is_offer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    is_hired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"))
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.text("false"), index=True)


class TestCheckbox(Base):
    """
    Test table for checkbox persistence functionality.
    Similar to Steam wishlist checkbox - stores a simple boolean state per user.
    """
    __tablename__ = "test_checkbox"

    user_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("users.id", ondelete="CASCADE"), 
        primary_key=True, 
        nullable=False
    )
    is_checked: Mapped[bool] = mapped_column(
        Boolean, 
        nullable=False, 
        default=False, 
        server_default=sa.text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        server_default=sa.text("now()")
    )

    # Relationship to User
    user: Mapped["User"] = relationship("User", back_populates="test_checkbox")


# Add relationship to User model (you'll need to add this to the User class too)


class SystemSettings(Base):
    """
    System-wide settings stored in the database.
    Each row represents a key-value pair where key is unique.
    Used for admin-configurable settings like signup grant configuration.
    """
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(length=255), primary_key=True, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=sa.text("now()"),
        server_onupdate=sa.text("now()"),
    )

