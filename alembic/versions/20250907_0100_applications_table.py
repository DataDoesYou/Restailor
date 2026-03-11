"""applications table for applied snapshots

Revision ID: 20250907_0100_applications
Revises: 20250906_normalize_judge_request_type
Create Date: 2025-09-07 01:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250907_0100_applications"
# Prior migration's actual revision id is shortened: 20250906_norm_judge_req_type
down_revision: Union[str, Sequence[str], None] = "20250906_norm_judge_req_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jd_hash", sa.Text(), nullable=False),
        sa.Column("base_hash", sa.Text(), nullable=False),
        sa.Column("applied_key", sa.Text(), nullable=False, unique=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("jd_url", sa.Text(), nullable=True),
        sa.Column("snapshot_enc", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Basic indexes
    op.create_index("ix_applications_user_id", "applications", ["user_id"])  # redundant with composite but explicit
    op.create_index("ix_applications_jd_hash", "applications", ["jd_hash"])  # filtering
    op.create_index("ix_applications_base_hash", "applications", ["base_hash"])  # filtering
    op.create_index("ix_applications_applied_key", "applications", ["applied_key"], unique=True)
    op.create_index("ix_applications_created_at", "applications", ["created_at"])  # recency queries
    # Composite for frequent lookups
    op.create_index("ix_applications_user_jd_base", "applications", ["user_id", "jd_hash", "base_hash"])  # uniqueness logical grouping

    # Trigger to auto-update updated_at (consistent with project style)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_set_timestamp() RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER set_timestamp_applications
        BEFORE UPDATE ON applications
        FOR EACH ROW
        EXECUTE PROCEDURE trg_set_timestamp();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS set_timestamp_applications ON applications")
    # (Function left as it's shared) - do not drop trg_set_timestamp if other tables use it.
    op.drop_index("ix_applications_user_jd_base", table_name="applications")
    op.drop_index("ix_applications_created_at", table_name="applications")
    op.drop_index("ix_applications_applied_key", table_name="applications")
    op.drop_index("ix_applications_base_hash", table_name="applications")
    op.drop_index("ix_applications_jd_hash", table_name="applications")
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")
