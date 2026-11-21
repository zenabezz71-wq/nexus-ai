"""Inbound webhooks: organizations.webhook_key.

The key authenticates POST /webhooks/leads/{key} without a user session so
external tools (form handlers, automation platforms) can push leads into a
workspace. Nullable: generated lazily the first time an admin opens the
Integrations page, rotatable at any time (old key dies immediately).
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_webhooks"
down_revision = "0007_platform_admin"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("webhook_key", sa.String(64), nullable=True))
        batch.create_index("ix_organizations_webhook_key", ["webhook_key"])


def downgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.drop_index("ix_organizations_webhook_key")
        batch.drop_column("webhook_key")
