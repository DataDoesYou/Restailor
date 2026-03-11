"""restore job stage and independent flag columns

Revision ID: 20250926_restore_job_stage_flags
Revises: 20250926_app_stage_flags_is
Create Date: 2025-09-26 15:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250926_restore_job_stage_flags"
down_revision = "20250926_app_stage_flags_is"
branch_labels = None
depends_on = None


_STAGE_CHECK = sa.text("stage IS NULL OR stage IN ('applied','interviewing','offer','hired')")


def upgrade() -> None:
    op.add_column("jobs", sa.Column("stage", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("has_interviewing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "jobs",
        sa.Column("has_offer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "jobs",
        sa.Column("has_hired", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    try:
        op.create_check_constraint("ck_jobs_stage_valid", "jobs", _STAGE_CHECK)
    except Exception:
        pass

    try:
        op.create_index(
            "ix_jobs_stage_user_not_deleted",
            "jobs",
            ["stage", "user_id"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    except Exception:
        pass

    try:
        op.create_index(
            "ix_jobs_user_stage_not_deleted",
            "jobs",
            ["user_id", "stage"],
            unique=False,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    except Exception:
        pass

    for name, column in (
        ("ix_jobs_has_interviewing", "has_interviewing"),
        ("ix_jobs_has_offer", "has_offer"),
        ("ix_jobs_has_hired", "has_hired"),
    ):
        try:
            op.create_index(name, "jobs", [column], unique=False)
        except Exception:
            pass

    # Drop the server defaults now that existing rows are backfilled.
    for column in ("has_interviewing", "has_offer", "has_hired"):
        try:
            op.alter_column("jobs", column, server_default=None)
        except Exception:
            pass


def downgrade() -> None:
    for name in (
        "ix_jobs_has_hired",
        "ix_jobs_has_offer",
        "ix_jobs_has_interviewing",
        "ix_jobs_user_stage_not_deleted",
        "ix_jobs_stage_user_not_deleted",
    ):
        try:
            op.drop_index(name, table_name="jobs")
        except Exception:
            pass

    try:
        op.drop_constraint("ck_jobs_stage_valid", "jobs", type_="check")
    except Exception:
        pass

    with op.batch_alter_table("jobs") as batch_op:
        for column in ("has_hired", "has_offer", "has_interviewing", "stage"):
            try:
                batch_op.drop_column(column)
            except Exception:
                pass
