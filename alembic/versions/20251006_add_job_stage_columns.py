"""add per-job stage tracking columns

Revision ID: 20251006_add_job_stage_columns
Revises: 20251005_single_snapshot_per_jd
Create Date: 2025-10-06 09:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251006_add_job_stage_columns"
down_revision = "20251005_single_snapshot_per_jd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("stage", sa.String(length=20), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "is_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "is_interviewing",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "is_offer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "is_hired",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_jobs_stage", "jobs", ["stage"])
    op.create_index("ix_jobs_is_applied", "jobs", ["is_applied"])
    op.create_index("ix_jobs_is_interviewing", "jobs", ["is_interviewing"])
    op.create_index("ix_jobs_is_offer", "jobs", ["is_offer"])
    op.create_index("ix_jobs_is_hired", "jobs", ["is_hired"])

    # Backfill the new columns from any application rows that were previously
    # bound to a specific job id.
    op.execute(
        """
        UPDATE jobs AS j
        SET stage = COALESCE(
                CASE
                    WHEN a.is_hired THEN 'hired'
                    WHEN a.is_offer THEN 'offer'
                    WHEN a.is_interviewing THEN 'interviewing'
                    WHEN a.is_applied THEN 'applied'
                    ELSE NULL
                END,
                j.stage
            ),
            is_applied = a.is_applied OR j.is_applied,
            is_interviewing = a.is_interviewing OR j.is_interviewing,
            is_offer = a.is_offer OR j.is_offer,
            is_hired = a.is_hired OR j.is_hired
        FROM applications AS a
        WHERE a.job_id = j.id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_is_hired", table_name="jobs")
    op.drop_index("ix_jobs_is_offer", table_name="jobs")
    op.drop_index("ix_jobs_is_interviewing", table_name="jobs")
    op.drop_index("ix_jobs_is_applied", table_name="jobs")
    op.drop_index("ix_jobs_stage", table_name="jobs")
    op.drop_column("jobs", "is_hired")
    op.drop_column("jobs", "is_offer")
    op.drop_column("jobs", "is_interviewing")
    op.drop_column("jobs", "is_applied")
    op.drop_column("jobs", "stage")
