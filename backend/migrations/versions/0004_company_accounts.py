"""Add company trial boundary and persistent authentication throttling. Existing records stay put."""
from alembic import op
import sqlalchemy as sa
revision="0004_company_accounts"
down_revision="0003_sales_feedback"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("organizations",sa.Column("trial_only",sa.Boolean(),server_default=sa.false(),nullable=False))
    op.create_table("auth_rate_buckets",sa.Column("key",sa.String(64),primary_key=True),sa.Column("used",sa.Integer(),nullable=False),sa.Column("expires_at",sa.Integer(),nullable=False))
    op.create_index("ix_auth_rate_buckets_expires_at","auth_rate_buckets",["expires_at"])

def downgrade():
    op.drop_table("auth_rate_buckets")
    op.drop_column("organizations","trial_only")
