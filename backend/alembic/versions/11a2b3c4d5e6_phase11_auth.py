"""phase 11 authentication and repository ownership

Revision ID: 11a2b3c4d5e6
Revises: a9b8c7d6e5f4
"""
from alembic import op
import sqlalchemy as sa

revision = "11a2b3c4d5e6"
down_revision = "a9b8c7d6e5f4"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.add_column(sa.Column("owner_user_id", sa.String(36), nullable=True))
        batch_op.create_index("ix_repositories_owner_user_id", ["owner_user_id"])
        batch_op.create_foreign_key("fk_repositories_owner_user_id_users", "users", ["owner_user_id"], ["id"])

def downgrade():
    with op.batch_alter_table("repositories") as batch_op:
        batch_op.drop_constraint("fk_repositories_owner_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_repositories_owner_user_id")
        batch_op.drop_column("owner_user_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
