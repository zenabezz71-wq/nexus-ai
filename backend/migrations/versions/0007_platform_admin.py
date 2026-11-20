"""Platform-owner super-admin: users.is_platform_admin, organizations.is_active + deleted_at.

Platform operators sit above every tenant org. The flag lives on the user, not
on any membership, so it is not tied to a single tenant. Suspension/soft-delete
state lives on the organization; login and membership resolution reject
suspended/deleted workspaces.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_platform_admin"
down_revision = "0006_foundation"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default="false"))
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("is_active")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("is_platform_admin")
