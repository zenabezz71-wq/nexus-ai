"""Phase 1 foundation: blueprint tenant tables, RBAC grants, PostgreSQL RLS.

Adds the multi-tenant CRM schema (teams, contacts, pipelines, stages, deals,
tasks, activities, notifications, integrations, ai_usage, subscriptions,
invoices), a grants column on memberships, organization_id on lead_sales, and
enables row level security on every tenant business table (PostgreSQL only;
SQLite test runs skip RLS). RLS is a database backstop: application queries
remain org-scoped in code.

Tenant policy: a row is visible/writable only when the request transaction set
app.organization_id to that organization, or the server marked the transaction
as a verified system actor (app.system_context = 'on', used by signed webhooks
and token-bearing unsubscribe endpoints only).
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_foundation"
down_revision = "0005_assistant"
branch_labels = None
depends_on = None

# Every tenant business table (existing + new). Identity tables (users,
# organizations, memberships) stay app-scoped: login must resolve a membership
# before any organization context exists. Global tables (rate buckets, quotas,
# the WhatsApp suppression list) have no organization and stay unscoped.
TENANT_TABLES = [
    "leads", "audit_logs", "sales_feedback", "lead_sales",
    "outreach_templates", "outreach_sends", "outreach_suppression",
    "whatsapp_sends", "assistant_conversations", "assistant_messages",
    "teams", "contacts", "pipelines", "pipeline_stages", "deals",
    "tasks", "activities", "notifications", "integrations", "ai_usage",
    "subscriptions", "invoices",
]

POLICY_SQL = """
CREATE POLICY tenant_isolation ON {table}
USING (current_setting('app.system_context', true) = 'on'
       OR organization_id = nullif(current_setting('app.organization_id', true), '')::int)
WITH CHECK (current_setting('app.system_context', true) = 'on'
       OR organization_id = nullif(current_setting('app.organization_id', true), '')::int)
"""


def _audit_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade():
    op.add_column("memberships", sa.Column("grants", sa.JSON, nullable=False, server_default="[]"))
    with op.batch_alter_table("lead_sales") as batch:
        batch.add_column(sa.Column("organization_id", sa.Integer, nullable=True))
        batch.create_foreign_key("fk_lead_sales_organization_id", "organizations", ["organization_id"], ["id"])
    op.execute("UPDATE lead_sales SET organization_id = (SELECT organization_id FROM leads WHERE leads.id = lead_sales.lead_id)")
    with op.batch_alter_table("lead_sales") as batch:
        batch.alter_column("organization_id", nullable=False)
        batch.create_index("ix_lead_sales_organization_id", ["organization_id"])

    op.create_table("teams",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])

    op.create_table("contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("position", sa.String(120), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_contacts_organization_id", "contacts", ["organization_id"])

    op.create_table("pipelines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_pipelines_organization_id", "pipelines", ["organization_id"])

    op.create_table("pipeline_stages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pipeline_id", sa.Integer, sa.ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("probability", sa.Integer, nullable=False),
        sa.Column("is_won", sa.Boolean, nullable=False),
        sa.Column("is_lost", sa.Boolean, nullable=False),
        *_audit_columns())
    op.create_index("ix_pipeline_stages_organization_id", "pipeline_stages", ["organization_id"])
    op.create_index("ix_pipeline_stages_pipeline_id", "pipeline_stages", ["pipeline_id"])

    op.create_table("deals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("pipeline_id", sa.Integer, sa.ForeignKey("pipelines.id"), nullable=True),
        sa.Column("stage_id", sa.Integer, sa.ForeignKey("pipeline_stages.id"), nullable=True),
        sa.Column("amount", sa.Float, nullable=True),
        sa.Column("currency", sa.String(12), nullable=False),
        sa.Column("expected_close", sa.Date, nullable=True),
        sa.Column("probability", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("next_step", sa.String(300), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_deals_organization_id", "deals", ["organization_id"])
    op.create_index("ix_deals_contact_id", "deals", ["contact_id"])
    op.create_index("ix_deals_status", "deals", ["status"])

    op.create_table("tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("deal_id", sa.Integer, sa.ForeignKey("deals.id"), nullable=True),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("assigned_to", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    op.create_table("activities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("deal_id", sa.Integer, sa.ForeignKey("deals.id"), nullable=True),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_activities_organization_id", "activities", ["organization_id"])
    op.create_index("ix_activities_contact_id", "activities", ["contact_id"])
    op.create_index("ix_activities_deal_id", "activities", ["deal_id"])
    op.create_index("ix_activities_lead_id", "activities", ["lead_id"])

    op.create_table("notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    op.create_table("integrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        *_audit_columns())
    op.create_index("ix_integrations_organization_id", "integrations", ["organization_id"])

    op.create_table("ai_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("feature", sa.String(60), nullable=False),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ai_usage_organization_id", "ai_usage", ["organization_id"])

    op.create_table("subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("seats", sa.Integer, nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])

    op.create_table("invoices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Integer, sa.ForeignKey("subscriptions.id"), nullable=True),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("currency", sa.String(12), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            bind.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            bind.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            bind.execute(sa.text(POLICY_SQL.format(table=table)))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            bind.execute(sa.text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
            bind.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    for table in ["invoices", "subscriptions", "ai_usage", "integrations", "notifications",
                  "activities", "tasks", "deals", "pipeline_stages", "pipelines", "contacts", "teams"]:
        op.drop_table(table)
    with op.batch_alter_table("lead_sales") as batch:
        batch.drop_index("ix_lead_sales_organization_id")
        batch.drop_column("organization_id")
    op.drop_column("memberships", "grants")
