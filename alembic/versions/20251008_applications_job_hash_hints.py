"""store job hash candidates on applications for fast lookup

Revision ID: 20251008_applications_job_hash
Revises: 20251007_applications_stage_cl
Create Date: 2025-10-08 09:00:00
"""
from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker

from backend.crypto_utils import decrypt_json
from backend.hash_utils import sha256_hex, normalize_text

try:  # pragma: no cover - migration fallback
    from restailor.input_gate import _normalize as gate_normalize  # type: ignore
except Exception:  # pragma: no cover
    def gate_normalize(value: str) -> str:  # type: ignore
        return normalize_text(value or "")


# revision identifiers, used by Alembic.
revision = "20251008_applications_job_hash"
down_revision = "20251007_applications_stage_cl"
branch_labels = None
depends_on = None


def _derive_job_hashes(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []

    resume_val = payload.get("resumeInput")
    jd_val = payload.get("jdInput")
    cand = payload.get("tailoredOutput")

    if not isinstance(resume_val, str) or not resume_val.strip():
        return []
    if not isinstance(jd_val, str) or not jd_val.strip():
        return []

    try:
        r_norm = gate_normalize(resume_val)
        j_norm = gate_normalize(jd_val)
    except Exception:
        return []

    hashes: list[str] = []

    def _push(candidate: str | None) -> None:
        if candidate and candidate not in hashes:
            hashes.append(candidate)

    try:
        _push(sha256_hex(r_norm + "\n" + j_norm + "\nFIT"))
    except Exception:
        pass
    try:
        _push(sha256_hex(r_norm + "\n" + j_norm))
    except Exception:
        pass

    cand_text: str | None = None
    if isinstance(cand, str):
        cand_text = cand
    elif cand is not None:
        try:
            cand_text = json.dumps(cand, ensure_ascii=False)
        except Exception:
            cand_text = str(cand)
    if isinstance(cand_text, str) and cand_text.strip():
        try:
            c_norm = gate_normalize(cand_text)
            _push(sha256_hex(r_norm + "\n" + j_norm + "\n" + c_norm + "\nJUDGE"))
        except Exception:
            pass

    return hashes


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "job_input_hashes",
            JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    applications = sa.Table(
        "applications",
        metadata,
        autoload_with=bind,
    )

    SessionLocal = sessionmaker(bind=bind)
    session: Session = SessionLocal()
    try:
        rows = session.execute(
            sa.select(applications.c.id, applications.c.snapshot_enc)
        ).fetchall()
        for app_id, snapshot_blob in rows:
            if not snapshot_blob:
                continue
            try:
                payload = decrypt_json(bytes(snapshot_blob), session=session)
            except Exception:
                payload = None
            hashes = _derive_job_hashes(payload)
            if hashes:
                session.execute(
                    sa.update(applications)
                    .where(applications.c.id == app_id)
                    .values(job_input_hashes=hashes)
                )
        session.commit()
    finally:
        session.close()


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("job_input_hashes")
