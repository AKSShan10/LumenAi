"""The AI helper shows which company notes (RAG) an answer is based on: helper_message.sources.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-16 18:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('helper_message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sources', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('helper_message', schema=None) as batch_op:
        batch_op.drop_column('sources')
