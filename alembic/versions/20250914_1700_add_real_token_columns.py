"""add real token & estimation metadata columns to charges

Revision ID: 20250914_1700_add_real_token_columns
Revises: 20250913_1310_merge_heads_output_models_branch
Create Date: 2025-09-14 17:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "20250914_1700_rt_cols"
# Corrected: previous value referenced a non-existent revision id; shortened to fit version_num length
down_revision = "20250913_1310_merge_heads"
branch_labels = None
depends_on = None

def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {c['name'] for c in inspector.get_columns('charges')}

    add_cols = []
    if 'prompt_tokens_real' not in existing_cols:
        add_cols.append(sa.Column("prompt_tokens_real", sa.Integer(), nullable=True))
    if 'completion_tokens_real' not in existing_cols:
        add_cols.append(sa.Column("completion_tokens_real", sa.Integer(), nullable=True))
    if 'reasoning_tokens_real' not in existing_cols:
        add_cols.append(sa.Column("reasoning_tokens_real", sa.Integer(), nullable=True))
    if 'token_estimation_method' not in existing_cols:
        add_cols.append(sa.Column("token_estimation_method", sa.Text(), nullable=True))

    if add_cols:
        with op.batch_alter_table("charges") as batch:
            for col in add_cols:
                batch.add_column(col)

    # Backfill only if the *_real columns exist now
    if {'prompt_tokens_real','completion_tokens_real','reasoning_tokens_real'} <= existing_cols or add_cols:
        op.execute(
            """
            UPDATE charges
            SET
                prompt_tokens_real = COALESCE(prompt_tokens_real, 0),
                completion_tokens_real = COALESCE(completion_tokens_real, 0),
                reasoning_tokens_real = COALESCE(reasoning_tokens_real, 0)
            WHERE prompt_tokens_real IS NULL
               OR completion_tokens_real IS NULL
               OR reasoning_tokens_real IS NULL;
            """
        )


def downgrade() -> None:
    with op.batch_alter_table("charges") as batch:
        batch.drop_column("token_estimation_method")
        batch.drop_column("reasoning_tokens_real")
        batch.drop_column("completion_tokens_real")
        batch.drop_column("prompt_tokens_real")
