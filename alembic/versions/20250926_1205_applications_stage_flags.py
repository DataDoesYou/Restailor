"""add independent stage flags to applications snapshots

Revision ID: 20250926_app_stage_flags
Revises: 20250926_snapshot_is_test
Create Date: 2025-09-26 12:05:00
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.crypto_utils import decrypt_json
from backend.hash_utils import normalize_text, sha256_hex

try:  # pragma: no cover - optional dependency may not be available during migrations
    from restailor.input_gate import _normalize as _gate_normalize  # type: ignore

    def _normalize_for_hash(value: str) -> str:
        return _gate_normalize(value or "")

except Exception:  # pragma: no cover - fallback when gate normalizer not importable

    def _normalize_for_hash(value: str) -> str:
        return normalize_text(value or "")


# revision identifiers, used by Alembic.
revision = "20250926_app_stage_flags"
down_revision = "20250926_snapshot_is_test"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "has_interviewing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "applications",
        sa.Column(
            "has_offer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "applications",
        sa.Column(
            "has_hired",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_index("ix_applications_has_interviewing", "applications", ["has_interviewing"], unique=False)
    op.create_index("ix_applications_has_offer", "applications", ["has_offer"], unique=False)
    op.create_index("ix_applications_has_hired", "applications", ["has_hired"], unique=False)

    bind = op.get_bind()
    _backfill_application_stage_flags(bind)

    for idx in ("ix_jobs_has_hired", "ix_jobs_has_offer", "ix_jobs_has_interviewing"):
        try:
            op.drop_index(idx, table_name="jobs")
        except Exception:
            pass

    with op.batch_alter_table("jobs") as batch_op:
        for col in ("has_hired", "has_offer", "has_interviewing"):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "has_interviewing",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "has_offer",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "has_hired",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )

    for idx, col in (
        ("ix_jobs_has_interviewing", "has_interviewing"),
        ("ix_jobs_has_offer", "has_offer"),
        ("ix_jobs_has_hired", "has_hired"),
    ):
        try:
            op.create_index(idx, "jobs", [col], unique=False)
        except Exception:
            pass

    bind = op.get_bind()
    _restore_job_stage_flags(bind)

    try:
        op.drop_index("ix_applications_has_hired", table_name="applications")
    except Exception:
        pass
    try:
        op.drop_index("ix_applications_has_offer", table_name="applications")
    except Exception:
        pass
    try:
        op.drop_index("ix_applications_has_interviewing", table_name="applications")
    except Exception:
        pass

    with op.batch_alter_table("applications") as batch_op:
        for col in ("has_hired", "has_offer", "has_interviewing"):
            try:
                batch_op.drop_column(col)
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


def _backfill_application_stage_flags(bind: sa.engine.Connection) -> None:
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
                        jobs.c.id,
                        jobs.c.input_hash,
                        jobs.c.has_interviewing,
                        jobs.c.has_offer,
                        jobs.c.has_hired,
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
                (job for job in ordered_candidates if isinstance(job.stage, str) and job.stage.strip()),
                None,
            )
            if chosen is None:
                chosen = ordered_candidates[0]

            interviewing = bool(getattr(chosen, "has_interviewing", False))
            offer = bool(getattr(chosen, "has_offer", False))
            hired = bool(getattr(chosen, "has_hired", False))

            stage_norm = ""
            stage_val = getattr(chosen, "stage", None)
            if isinstance(stage_val, str):
                stage_norm = stage_val.strip().lower()

            if not any((interviewing, offer, hired)):
                if stage_norm == "interviewing":
                    interviewing = True
                elif stage_norm == "offer":
                    offer = True
                elif stage_norm == "hired":
                    hired = True

            session.execute(
                applications.update()
                .where(applications.c.id == app_id)
                .values(
                    has_interviewing=interviewing,
                    has_offer=offer,
                    has_hired=hired,
                )
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


def _restore_job_stage_flags(bind: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    applications = sa.Table("applications", metadata, autoload_with=bind)
    jobs = sa.Table("jobs", metadata, autoload_with=bind)

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    try:
        rows = session.execute(
            sa.select(
                applications.c.user_id,
                applications.c.snapshot_enc,
                applications.c.has_interviewing,
                applications.c.has_offer,
                applications.c.has_hired,
            )
        ).fetchall()

        job_flag_map: dict[Any, dict[str, bool]] = defaultdict(lambda: {"interviewing": False, "offer": False, "hired": False})

        for user_id, snapshot_blob, flag_interviewing, flag_offer, flag_hired in rows:
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
                        jobs.c.id,
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
                (job for job in ordered_candidates if isinstance(job.stage, str) and job.stage.strip()),
                None,
            )
            if chosen is None:
                chosen = ordered_candidates[0]

            bucket = job_flag_map[chosen.id]
            bucket["interviewing"] = bucket["interviewing"] or bool(flag_interviewing)
            bucket["offer"] = bucket["offer"] or bool(flag_offer)
            bucket["hired"] = bucket["hired"] or bool(flag_hired)

        updates_since_commit = 0
        for job_id, flags in job_flag_map.items():
            session.execute(
                jobs.update()
                .where(jobs.c.id == job_id)
                .values(
                    has_interviewing=flags["interviewing"],
                    has_offer=flags["offer"],
                    has_hired=flags["hired"],
                )
            )
            updates_since_commit += 1
            if updates_since_commit >= 200:
                session.commit()
                updates_since_commit = 0

        session.execute(
            sa.text(
                """
                UPDATE jobs
                SET has_interviewing = TRUE
                WHERE stage = 'interviewing'
                """
            )
        )
        session.execute(
            sa.text(
                """
                UPDATE jobs
                SET has_offer = TRUE
                WHERE stage = 'offer'
                """
            )
        )
        session.execute(
            sa.text(
                """
                UPDATE jobs
                SET has_hired = TRUE
                WHERE stage = 'hired'
                """
            )
        )

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
