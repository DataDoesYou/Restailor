"""consolidate applications snapshot projections

Revision ID: 20251007_applications_stage_cl
Revises: 20251006_add_job_stage_columns
Create Date: 2025-10-07 09:00:00
"""
from __future__ import annotations

from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from backend.crypto_utils import decrypt_json


JD_TEXT_NORM_LIMIT = 800


# revision identifiers, used by Alembic.
revision = "20251007_applications_stage_cl"
down_revision = "20251006_add_job_stage_columns"
branch_labels = None
depends_on = None


def _compute_snippet(text: str | None, limit: int = 500) -> str | None:
    if not isinstance(text, str):
        return None
    snippet = " ".join(text.split())
    return snippet[:limit] if snippet else None


def _normalize_for_search(text: str | None) -> str | None:
    if not isinstance(text, str):
        return None
    lowered = text.lower()
    normalized = " ".join(lowered.split())
    return normalized[:JD_TEXT_NORM_LIMIT] if normalized else None


def _extract_jd_text(snapshot: Any) -> str | None:
    if isinstance(snapshot, dict):
        jd_val = snapshot.get("jdInput")
        if isinstance(jd_val, str):
            return jd_val
    return None


def upgrade() -> None:
    op.drop_index("ix_applications_applied_key_canonical", table_name="applications", if_exists=True)

    op.add_column("applications", sa.Column("jd_snippet", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("jd_text_norm", sa.Text(), nullable=True))

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_applications_jd_text_norm",
        "applications",
        ["jd_text_norm"],
        postgresql_using="gin",
        postgresql_ops={"jd_text_norm": "gin_trgm_ops"},
    )

    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("applied_key_canonical")

    bind = op.get_bind()
    metadata = sa.MetaData()
    applications = sa.Table("applications", metadata, autoload_with=bind)

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    try:
        rows = session.execute(sa.select(applications.c.id, applications.c.snapshot_enc)).fetchall()
        for app_id, snapshot_blob in rows:
            if not snapshot_blob:
                continue
            try:
                payload = decrypt_json(bytes(snapshot_blob), session=session)
            except Exception:
                payload = None
            jd_text = _extract_jd_text(payload) if isinstance(payload, dict) else None
            snippet = _compute_snippet(jd_text)
            normalized = _normalize_for_search(jd_text)
            if snippet or normalized:
                session.execute(
                    sa.update(applications)
                    .where(applications.c.id == app_id)
                    .values(jd_snippet=snippet, jd_text_norm=normalized)
                )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    applications = sa.Table("applications", metadata, autoload_with=bind)

    op.drop_index("ix_applications_jd_text_norm", table_name="applications", if_exists=True)

    op.add_column("applications", sa.Column("applied_key_canonical", sa.Text(), nullable=True))

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    try:
        session.execute(
            sa.update(applications)
            .values(applied_key_canonical=applications.c.applied_key)
        )
        session.commit()
    finally:
        session.close()

    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("jd_text_norm")
        batch_op.drop_column("jd_snippet")

    op.create_index(
        "ix_applications_applied_key_canonical",
        "applications",
        ["applied_key_canonical"],
    )
