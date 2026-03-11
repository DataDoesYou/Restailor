"""normalize judgeN request types to judge and set model_count

Revision ID: 20250906_norm_judge_req_type
Revises: 20250906_model_count 20250906_expand_charge_req_types
Create Date: 2025-09-06

NOTE: Original revision id was longer than 32 chars (alembic_version.version_num varchar(32)).
It has been shortened to comply with the column limit.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250906_norm_judge_req_type"
down_revision: Union[str, Sequence[str], None] = ("20250906_model_count", "20250906_expand_charge_req_types")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:  # pragma: no cover
    conn = op.get_bind()
    # Collapse judgeN -> judge while preserving N in model_count (dynamic N; existing max N=8)
    conn.execute(sa.text(
        """
        UPDATE charges
        SET model_count = CASE
                WHEN request_type ~ '^judge([0-9]+)$' THEN GREATEST(1, (regexp_replace(request_type, '^judge([0-9]+)$', '\\1'))::int)
                ELSE model_count
            END,
            request_type = CASE
                WHEN request_type ~ '^judge([0-9]+)$' THEN 'judge'
                ELSE request_type
            END
        WHERE request_type ~ '^judge([0-9]+)$';
        """
    ))
    # Ensure plain judge rows have model_count >=1
    conn.execute(sa.text("UPDATE charges SET model_count = 1 WHERE request_type = 'judge' AND (model_count IS NULL OR model_count < 1)"))


def downgrade() -> None:  # pragma: no cover
    # Irreversible; judgeN detail lost.
    pass
