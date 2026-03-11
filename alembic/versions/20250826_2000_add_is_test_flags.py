"""add is_test boolean flags to core tables and backfill test data

Revision ID: 20250826_2000_add_is_test_flags
Revises: 20250826_1600_add_email_logs
Create Date: 2025-08-26 20:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250826_2000_add_is_test_flags'
down_revision = '20250826_1600_add_email_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_test with false default
    for table in ("users", "jobs", "job_outputs", "charges", "credit_ledger", "user_balance", "email_logs"):
        op.add_column(table, sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.create_index(f"ix_{table}_is_test", table, ["is_test"], unique=False)

    # Backfill heuristics
    # - users: username endswith @example.com OR lower(username) like %test%/%demo%/%e2e%/%playwright%
    op.execute(
        """
        UPDATE users SET is_test = true
        WHERE (
            lower(username) LIKE '%@example.com' OR
            lower(username) LIKE '%test%' OR
            lower(username) LIKE '%demo%' OR
            lower(username) LIKE '%e2e%' OR
            lower(username) LIKE '%playwright%'
        )
        """
    )

    # - jobs: client_id patterns or source_page in ('Test','Model Benchmark') or user is_test
    op.execute(
        """
        UPDATE jobs SET is_test = true
        WHERE (
            lower(coalesce(client_id, '')) LIKE 'test%' OR
            lower(coalesce(client_id, '')) LIKE 'e2e%' OR
            lower(coalesce(client_id, '')) LIKE 'benchmark:%' OR
            lower(coalesce(client_id, '')) LIKE 'admin-tests%' OR
            lower(coalesce(client_id, '')) LIKE 'limits-%' OR
            coalesce(source_page, '') IN ('Test','Model Benchmark') OR
            user_id IN (SELECT id FROM users WHERE is_test = true)
        )
        """
    )

    # - job_outputs: join jobs
    op.execute(
        """
        UPDATE job_outputs jo
        SET is_test = true
        FROM jobs j
        WHERE jo.job_id = j.id AND j.is_test = true
        """
    )

    # - charges: provider='testprov' OR job_id maps to test job OR user is_test
    op.execute(
        """
        UPDATE charges c
        SET is_test = true
        WHERE (
            lower(provider) = 'testprov' OR
            (job_id IS NOT NULL AND job_id IN (SELECT id FROM jobs WHERE is_test = true)) OR
            user_id IN (SELECT id FROM users WHERE is_test = true)
        )
        """
    )

    # - credit_ledger: user is_test
    op.execute(
        """
        UPDATE credit_ledger cl SET is_test = true
        WHERE user_id IN (SELECT id FROM users WHERE is_test = true)
        """
    )

    # - user_balance: user is_test
    op.execute(
        """
        UPDATE user_balance ub SET is_test = true
        WHERE user_id IN (SELECT id FROM users WHERE is_test = true)
        """
    )

    # - email_logs: recipient @example.com or client_id patterns or user is_test
    op.execute(
        """
        UPDATE email_logs el SET is_test = true
        WHERE (
            lower(coalesce(recipient,'')) LIKE '%@example.com' OR
            lower(coalesce(client_id,'')) LIKE 'test%' OR
            lower(coalesce(client_id,'')) LIKE 'e2e%' OR
            lower(coalesce(client_id,'')) LIKE 'benchmark:%' OR
            lower(coalesce(client_id,'')) LIKE 'admin-tests%' OR
            lower(coalesce(client_id,'')) LIKE 'limits-%' OR
            user_id IN (SELECT id FROM users WHERE is_test = true)
        )
        """
    )


def downgrade() -> None:
    for table in ("email_logs", "user_balance", "credit_ledger", "charges", "job_outputs", "jobs", "users"):
        op.drop_index(f"ix_{table}_is_test", table_name=table)
        op.drop_column(table, "is_test")
