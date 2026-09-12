"""phase 8 generated documentation artifacts

Revision ID: f8a9b0c1d2e3
Revises: e7f1a2b3c4d5
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "e7f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documentation_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("format", sa.String(length=20), nullable=False, server_default="markdown"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("used_llm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("llm_provider", sa.String(length=50), nullable=True),
        sa.Column("llm_model", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("documentation_artifacts")
