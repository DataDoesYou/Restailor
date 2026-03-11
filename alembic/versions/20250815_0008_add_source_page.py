from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250815_0008_add_source_page'
down_revision = '20250815_0007'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('jobs', sa.Column('source_page', sa.String(length=50), nullable=True))
    op.create_index('ix_jobs_source_page', 'jobs', ['source_page'], unique=False)


def downgrade():
    op.drop_index('ix_jobs_source_page', table_name='jobs')
    op.drop_column('jobs', 'source_page')
