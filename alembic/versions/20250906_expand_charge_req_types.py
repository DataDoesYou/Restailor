"""placeholder: lost migration expand_charge_req_types

This placeholder recreates the missing revision ID so the existing database
state (which reports this revision in alembic_version) can be advanced to the
newer migrations. The original migration's effects are assumed to be already
present in the schema; no operations are performed here.

Revision ID: 20250906_expand_charge_req_types
Revises: v_30_1700_pv_int
Create Date: 2025-09-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op  # noqa: F401  (imported for symmetry, unused)
import sqlalchemy as sa  # noqa: F401

revision: str = "20250906_expand_charge_req_types"
down_revision: Union[str, Sequence[str], None] = "v_30_1700_pv_int"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:  # pragma: no cover - no-op
    # Intentionally empty; original migration file lost.
    pass


def downgrade() -> None:  # pragma: no cover - no-op
    # Intentionally empty; cannot safely reverse unknown operations.
    pass
