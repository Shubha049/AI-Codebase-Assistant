"""phase 2: code symbols, imports, dependency edges, repo analysis fields

Revision ID: 49013cae4798
Revises: 327309d63eb4
Create Date: 2026-08-15 14:06:09.748097
"""
from alembic import op
import sqlalchemy as sa


revision = '49013cae4798'
down_revision = '327309d63eb4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('code_symbols',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('repository_id', sa.String(length=36), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=False),
    sa.Column('language', sa.String(length=50), nullable=False),
    sa.Column('symbol_type', sa.Enum('FUNCTION', 'METHOD', 'CLASS', 'ARROW_FUNCTION', name='symboltype'), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('parent_name', sa.String(length=255), nullable=True),
    sa.Column('start_line', sa.Integer(), nullable=False),
    sa.Column('end_line', sa.Integer(), nullable=False),
    sa.Column('docstring', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dependency_edges',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('repository_id', sa.String(length=36), nullable=False),
    sa.Column('source_file', sa.String(length=1024), nullable=False),
    sa.Column('target_file', sa.String(length=1024), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('import_statements',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('repository_id', sa.String(length=36), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=False),
    sa.Column('language', sa.String(length=50), nullable=False),
    sa.Column('module', sa.String(length=1024), nullable=False),
    sa.Column('imported_names', sa.JSON(), nullable=False),
    sa.Column('line_number', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # SQLite can't ALTER COLUMN directly — batch mode recreates the table
    # under the hood. Hand-edited from the raw autogenerate output, which
    # emitted a bare op.alter_column() that fails on SQLite with a plain
    # "near ALTER: syntax error" (verified directly before this fix).
    with op.batch_alter_table('indexing_jobs') as batch_op:
        batch_op.alter_column(
            'stage',
            existing_type=sa.VARCHAR(length=10),
            type_=sa.Enum('EXTRACTION', 'SCANNING', 'PARSING', 'DEPENDENCY_GRAPH', 'FRAMEWORK_DETECTION', 'CHUNKING', 'EMBEDDING', name='jobstage'),
            existing_nullable=False,
        )

    # Hand-edited: raw autogenerate emitted `nullable=False` with no
    # server_default, which fails on any table that already has rows
    # (SQLite can't backfill a NOT NULL column with no default). Verified
    # this would break against a non-empty repositories table before
    # adding the defaults below.
    op.add_column('repositories', sa.Column('frameworks', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('repositories', sa.Column('build_systems', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('repositories', sa.Column('symbol_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('repositories', sa.Column('parsed_file_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('repositories', sa.Column('dependency_edge_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('repositories', 'dependency_edge_count')
    op.drop_column('repositories', 'parsed_file_count')
    op.drop_column('repositories', 'symbol_count')
    op.drop_column('repositories', 'build_systems')
    op.drop_column('repositories', 'frameworks')
    with op.batch_alter_table('indexing_jobs') as batch_op:
        batch_op.alter_column(
            'stage',
            existing_type=sa.Enum('EXTRACTION', 'SCANNING', 'PARSING', 'DEPENDENCY_GRAPH', 'FRAMEWORK_DETECTION', 'CHUNKING', 'EMBEDDING', name='jobstage'),
            type_=sa.VARCHAR(length=10),
            existing_nullable=False,
        )
    op.drop_table('import_statements')
    op.drop_table('dependency_edges')
    op.drop_table('code_symbols')
