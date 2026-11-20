"""AI sales assistant conversations. Additive only."""
from alembic import op
import sqlalchemy as sa
revision = "0005_assistant"
down_revision = "0004_company_accounts"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("assistant_conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("lead_id", sa.Integer, sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("needs_attention", sa.Boolean, nullable=False),
        sa.Column("handoff_reason", sa.String(300), nullable=False),
        sa.Column("state", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_assistant_conversations_organization_id", "assistant_conversations", ["organization_id"])
    op.create_index("ix_assistant_conversations_lead_id", "assistant_conversations", ["lead_id"])
    op.create_table("assistant_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("organization_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("assistant_conversations.id"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("delivery", sa.String(30), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_assistant_messages_organization_id", "assistant_messages", ["organization_id"])
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])
    op.create_index("ix_assistant_messages_provider_message_id", "assistant_messages", ["provider_message_id"])

def downgrade():
    op.drop_table("assistant_messages")
    op.drop_table("assistant_conversations")
