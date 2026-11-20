"""Add separate outreach tables without changing existing lead rows."""
from alembic import op
import sqlalchemy as sa
revision = "0002_outreach"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("outreach_templates", sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), primary_key=True), sa.Column("subject", sa.String(200), nullable=False), sa.Column("body", sa.Text, nullable=False))
    for table, size, with_subject, constraint in [("outreach_sends", 320, True, "uq_outreach_recipient"), ("whatsapp_sends", 40, False, "uq_whatsapp_recipient")]:
        columns = [sa.Column("id", sa.Integer, primary_key=True), sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False), sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=False), sa.Column("recipient", sa.String(size), nullable=False), sa.Column("body", sa.Text, nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("provider_message_id", sa.String(500), nullable=False), sa.Column("error", sa.String(300), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]
        if with_subject: columns.append(sa.Column("subject", sa.String(200), nullable=False))
        op.create_table(table, *columns, sa.UniqueConstraint("organization_id", "recipient", name=constraint))
        op.create_index("ix_"+table+"_organization_id", table, ["organization_id"])
        op.create_index("ix_"+table+"_lead_id", table, ["lead_id"])
    op.create_index("ix_whatsapp_sends_provider_message_id", "whatsapp_sends", ["provider_message_id"])
    for table in ("outreach_quota", "whatsapp_quota"):
        op.create_table(table, sa.Column("day", sa.String(10), primary_key=True), sa.Column("used", sa.Integer, nullable=False))
    op.create_table("outreach_suppressions", sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), primary_key=True), sa.Column("recipient", sa.String(320), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("whatsapp_suppressions", sa.Column("recipient", sa.String(40), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    for table in ("whatsapp_suppressions", "outreach_suppressions", "whatsapp_quota", "outreach_quota", "whatsapp_sends", "outreach_sends", "outreach_templates"):
        op.drop_table(table)
