"""phase 5 QA conversation memory

Revision ID: c1e4b7a9f5d2
Revises: 88a6a86578b7
"""
from alembic import op
import sqlalchemy as sa

revision = "c1e4b7a9f5d2"
down_revision = "88a6a86578b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "qa_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "qa_conversation_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("qa_conversations.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("qa_conversation_messages")
    op.drop_table("qa_conversations")
