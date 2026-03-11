"""DEPRECATED duplicate migration — no-op.

This file was superseded by the short-ID migration `add_job_access_token_0100`.
To keep Alembic history linear and avoid multiple heads, this migration is kept
as a no-op depending on the short-ID migration.

Revision ID: add_job_access_token_0101
Revises: add_job_access_token_0100
Create Date: 2025-08-15 01:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import secrets


# revision identifiers, used by Alembic.
revision = "add_job_access_token_0101"
down_revision = "add_job_access_token_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op; real changes are in add_job_access_token_0100
    pass


def downgrade() -> None:
    # No-op to keep symmetry
    pass
