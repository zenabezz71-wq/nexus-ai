"""Lead assignment and append-only sales feedback."""
from alembic import op
import sqlalchemy as sa
revision = "0003_sales_feedback"
down_revision = "0002_outreach"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("lead_sales", sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), primary_key=True), sa.Column("assigned_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True))
    op.create_table("sales_feedback", sa.Column("id", sa.Integer, primary_key=True), sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False), sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=False), sa.Column("author_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False), sa.Column("body", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_sales_feedback_organization_id", "sales_feedback", ["organization_id"])
    op.create_index("ix_sales_feedback_lead_id", "sales_feedback", ["lead_id"])

def downgrade():
    op.drop_table("sales_feedback")
    op.drop_table("lead_sales")
