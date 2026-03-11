"""move stage data from jobs to applications

Revision ID: 20250926_app_stage
Revises: 20250926_app_stage_flags
Create Date: 2025-09-26 13:00:00
"""
from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.crypto_utils import decrypt_json
from backend.hash_utils import normalize_text, sha256_hex

try:  # pragma: no cover - optional dependency during offline migrations
    from restailor.input_gate import _normalize as _gate_normalize  # type: ignore

    def _normalize_for_hash(value: str) -> str:
        return _gate_normalize(value or "")

except Exception:  # pragma: no cover - fallback when gate normalizer not importable

    def _normalize_for_hash(value: str) -> str:
        return normalize_text(value or "")


# revision identifiers, used by Alembic.
revision = "20250926_app_stage"
down_revision = "20250926_app_stage_flags"
branch_labels = None
depends_on = None

_STAGE_VALUES = {"applied", "interviewing", "offer", "hired"}
_STAGE_PRIORITY = {"applied": 0, "interviewing": 1, "offer": 2, "hired": 3}


def upgrade() -> None:
    op.add_column("applications", sa.Column("stage", sa.Text(), nullable=True))
    op.create_index("ix_applications_stage_user", "applications", ["stage", "user_id"], unique=False)

    bind = op.get_bind()
    _backfill_application_stage(bind)

    for idx in ("ix_jobs_user_stage_not_deleted", "ix_jobs_stage_user_not_deleted"):
        try:
            op.drop_index(idx, table_name="jobs")
        except Exception:
            pass

    with op.batch_alter_table("jobs") as batch_op:
        try:
            batch_op.drop_constraint("ck_jobs_stage_valid", type_="check")
        except Exception:
            pass
        try:
            batch_op.drop_column("stage")
        except Exception:
            pass


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("stage", sa.Text(), nullable=True))

    bind = op.get_bind()
    _restore_job_stage(bind)

    try:
        op.create_check_constraint(
            "ck_jobs_stage_valid",
            "jobs",
            sa.text("stage IS NULL OR stage IN ('applied','interviewing','offer','hired')"),
        )
    except Exception:
        pass

    for idx, cols in (
        ("ix_jobs_stage_user_not_deleted", ["stage", "user_id"]),
        ("ix_jobs_user_stage_not_deleted", ["user_id", "stage"]),
    ):
        try:
            op.create_index(idx, "jobs", cols, unique=False, postgresql_where=sa.text("deleted_at IS NULL"))
        except Exception:
            pass

    try:
        op.drop_index("ix_applications_stage_user", table_name="applications")
    except Exception:
        pass

    with op.batch_alter_table("applications") as batch_op:
        try:
            batch_op.drop_column("stage")
        except Exception:
            pass


def _coerce_tailored_output(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _candidate_input_hashes(snapshot: Any) -> list[str]:
    if not isinstance(snapshot, dict):
        return []

    jd_val = snapshot.get("jdInput")
    base_val = snapshot.get("resumeInput")
    if not (isinstance(jd_val, str) and isinstance(base_val, str) and jd_val and base_val):
        return []

    try:
        resume_norm = _normalize_for_hash(base_val)
        jd_norm = _normalize_for_hash(jd_val)
    except Exception:
        return []

    hashes: list[str] = []
    try:
        hashes.append(sha256_hex(f"{resume_norm}\n{jd_norm}\nFIT"))
    except Exception:
        pass
    try:
        hashes.append(sha256_hex(f"{resume_norm}\n{jd_norm}"))
    except Exception:
        pass

    cand_val = _coerce_tailored_output(snapshot.get("tailoredOutput"))
    if cand_val:
        try:
            cand_norm = _normalize_for_hash(cand_val)
            hashes.append(sha256_hex(f"{resume_norm}\n{jd_norm}\n{cand_norm}\nJUDGE"))
        except Exception:
            pass

    seen: set[str] = set()
    unique: list[str] = []
    for item in hashes:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _normalize_stage(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    norm = value.strip().lower()
    if norm in _STAGE_VALUES:
        return norm
    return None


def _backfill_application_stage(bind: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    applications = sa.Table("applications", metadata, autoload_with=bind)
    jobs = sa.Table("jobs", metadata, autoload_with=bind)

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    updates_since_commit = 0
    try:
        rows = session.execute(
            sa.select(
                applications.c.id,
                applications.c.user_id,
                applications.c.snapshot_enc,
            )
        ).fetchall()

        if not rows:
            session.commit()
            return

        for app_id, user_id, snapshot_blob in rows:
            if not snapshot_blob:
                continue
            try:
                payload = decrypt_json(bytes(snapshot_blob), session=session)
            except Exception:
                continue

            candidate_hashes = _candidate_input_hashes(payload)
            if not candidate_hashes:
                continue

            try:
                job_rows = session.execute(
                    sa.select(
                        jobs.c.input_hash,
                        jobs.c.stage,
                        jobs.c.created_at,
                    )
                    .where(
                        jobs.c.user_id == user_id,
                        jobs.c.deleted_at.is_(None),
                        jobs.c.input_hash.in_(candidate_hashes),
                    )
                    .order_by(jobs.c.input_hash.asc(), jobs.c.created_at.desc())
                ).fetchall()
            except Exception:
                continue

            if not job_rows:
                continue

            latest_by_hash: dict[str, Any] = {}
            for job in job_rows:
                ih = job.input_hash
                if ih not in latest_by_hash:
                    latest_by_hash[ih] = job

            ordered_candidates = [latest_by_hash[ih] for ih in candidate_hashes if ih in latest_by_hash]
            if not ordered_candidates:
                continue

            chosen = next(
                (job for job in ordered_candidates if _normalize_stage(job.stage)),
                None,
            )
            if chosen is None:
                chosen = ordered_candidates[0]

            stage_norm = _normalize_stage(getattr(chosen, "stage", None))
            if not stage_norm:
                continue

            session.execute(
                applications.update()
                .where(applications.c.id == app_id)
                .values(stage=stage_norm)
            )
            updates_since_commit += 1
            if updates_since_commit >= 200:
                session.commit()
                updates_since_commit = 0

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _restore_job_stage(bind: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    applications = sa.Table("applications", metadata, autoload_with=bind)
    jobs = sa.Table("jobs", metadata, autoload_with=bind)

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    updates_since_commit = 0
    try:
        rows = session.execute(
            sa.select(
                applications.c.user_id,
                applications.c.snapshot_enc,
                applications.c.stage,
            )
        ).fetchall()

        if not rows:
            session.commit()
            return

        stage_by_job: dict[Any, str] = {}

        for user_id, snapshot_blob, stage_value in rows:
            stage_norm = _normalize_stage(stage_value)
            if not snapshot_blob or not stage_norm:
                continue

            try:
                payload = decrypt_json(bytes(snapshot_blob), session=session)
            except Exception:
                continue

            candidate_hashes = _candidate_input_hashes(payload)
            if not candidate_hashes:
                continue

            try:
                job_rows = session.execute(
                    sa.select(
                        jobs.c.id,
                        jobs.c.input_hash,
                        jobs.c.created_at,
                    )
                    .where(
                        jobs.c.user_id == user_id,
                        jobs.c.deleted_at.is_(None),
                        jobs.c.input_hash.in_(candidate_hashes),
                    )
                    .order_by(jobs.c.input_hash.asc(), jobs.c.created_at.desc())
                ).fetchall()
            except Exception:
                continue

            if not job_rows:
                continue

            latest_by_hash: dict[str, Any] = {}
            for job in job_rows:
                ih = job.input_hash
                if ih not in latest_by_hash:
                    latest_by_hash[ih] = job

            ordered_candidates = [latest_by_hash[ih] for ih in candidate_hashes if ih in latest_by_hash]
            if not ordered_candidates:
                continue

            chosen = ordered_candidates[0]
            job_id = getattr(chosen, "id", None)
            if job_id is None:
                continue

            existing_stage = stage_by_job.get(job_id)
            if existing_stage is None or _STAGE_PRIORITY[stage_norm] > _STAGE_PRIORITY[existing_stage]:
                stage_by_job[job_id] = stage_norm

        for job_id, stage_norm in stage_by_job.items():
            session.execute(
                jobs.update()
                .where(jobs.c.id == job_id)
                .values(stage=stage_norm)
            )
            updates_since_commit += 1
            if updates_since_commit >= 200:
                session.commit()
                updates_since_commit = 0

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
