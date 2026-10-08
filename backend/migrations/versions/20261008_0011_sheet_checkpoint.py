"""Sheet checkpoint: job.sheet_checkpoint_row keeps the last sheet row that is finished.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-08 08:30:50.490832
"""
import sqlalchemy as sa
from alembic import op

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Row 1 of the sheet holds the titles, so 1 means "no application row is finished yet".
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sheet_checkpoint_row', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('sheet_checkpoint_row')
