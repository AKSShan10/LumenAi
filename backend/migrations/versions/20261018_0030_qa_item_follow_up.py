"""Q&A analysis: a suggested follow-up question per answer (qa_item.follow_up).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-18 18:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('follow_up', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.drop_column('follow_up')
