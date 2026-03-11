"""add user settings fields to users

Revision ID: 20250824_0200_user_settings
Revises: 41d4f6519ee9
Create Date: 2025-08-24 02:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20250824_0200_user_settings"
down_revision: Union[str, Sequence[str], None] = "41d4f6519ee9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding user settings fields."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "public_profile",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "dont_save_future_data",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "deleted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "credits_forfeited_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    """Downgrade schema by removing user settings fields."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("credits_forfeited_at")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("dont_save_future_data")
        batch_op.drop_column("public_profile")
