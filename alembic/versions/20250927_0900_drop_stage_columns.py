"""drop legacy stage columns in favor of flag projections

Revision ID: 20250927_drop_stage_columns
Revises: 20250926_restore_job_stage_flags
Create Date: 2025-09-27 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250927_drop_stage_columns"
down_revision = "20250926_restore_job_stage_flags"
branch_labels = None
depends_on = None


def _sync_job_flags_from_stage() -> None:
    op.execute(
        sa.text(
            """
            UPDATE jobs
            SET
                has_interviewing = CASE
                    WHEN stage IN ('interviewing','offer','hired') THEN TRUE
                    ELSE has_interviewing
                END,
                has_offer = CASE
                    WHEN stage IN ('offer','hired') THEN TRUE
                    ELSE has_offer
                END,
                has_hired = CASE
                    WHEN stage = 'hired' THEN TRUE
                    ELSE has_hired
                END
            WHERE stage IS NOT NULL
            """
        )
    )


def _sync_application_flags_from_stage() -> None:
    op.execute(
        sa.text(
            """
            UPDATE applications
            SET
                is_interviewing = CASE
                    WHEN stage IN ('interviewing','offer','hired') THEN TRUE
                    ELSE is_interviewing
                END,
                is_offer = CASE
                    WHEN stage IN ('offer','hired') THEN TRUE
                    ELSE is_offer
                END,
                is_hired = CASE
                    WHEN stage = 'hired' THEN TRUE
                    ELSE is_hired
                END
            WHERE stage IS NOT NULL
            """
        )
    )


def upgrade() -> None:
    _sync_job_flags_from_stage()
    _sync_application_flags_from_stage()

    for name in (
        "ix_jobs_stage_user_not_deleted",
        "ix_jobs_user_stage_not_deleted",
    ):
        try:
            op.drop_index(name, table_name="jobs")
        except Exception:
            pass

    try:
        op.drop_constraint("ck_jobs_stage_valid", "jobs", type_="check")
    except Exception:
        pass

    try:
        op.drop_index("ix_applications_stage_user", table_name="applications")
    except Exception:
        pass

    with op.batch_alter_table("jobs") as batch_op:
        try:
            batch_op.drop_column("stage")
        except Exception:
            pass

    with op.batch_alter_table("applications") as batch_op:
        try:
            batch_op.drop_column("stage")
        except Exception:
            pass


def _restore_job_stage_from_flags() -> None:
    op.execute(
        sa.text(
            """
            UPDATE jobs
            SET stage = CASE
                WHEN has_hired IS TRUE THEN 'hired'
                WHEN has_offer IS TRUE THEN 'offer'
                WHEN has_interviewing IS TRUE THEN 'interviewing'
                ELSE 'applied'
            END
            """
        )
    )


def _restore_application_stage_from_flags() -> None:
    op.execute(
        sa.text(
            """
            UPDATE applications
            SET stage = CASE
                WHEN is_hired IS TRUE THEN 'hired'
                WHEN is_offer IS TRUE THEN 'offer'
                WHEN is_interviewing IS TRUE THEN 'interviewing'
                ELSE 'applied'
            END
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("stage", sa.Text(), nullable=True))

    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("stage", sa.Text(), nullable=True))

    _restore_job_stage_from_flags()
    _restore_application_stage_from_flags()

    try:
        op.create_check_constraint(
            "ck_jobs_stage_valid",
            "jobs",
            sa.text("stage IS NULL OR stage IN ('applied','interviewing','offer','hired')"),
        )
    except Exception:
        pass

    for name, columns in (
        (
            "ix_jobs_stage_user_not_deleted",
            ["stage", "user_id"],
        ),
        (
            "ix_jobs_user_stage_not_deleted",
            ["user_id", "stage"],
        ),
    ):
        try:
            op.create_index(
                name,
                "jobs",
                columns,
                unique=False,
                postgresql_where=sa.text("deleted_at IS NULL"),
            )
        except Exception:
            pass

    try:
        op.create_index("ix_applications_stage_user", "applications", ["stage", "user_id"], unique=False)
    except Exception:
        pass
