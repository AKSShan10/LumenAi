"""Job prompt: the short text the interviewer typed for the AI is kept with the job.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06 10:16:35.512772
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default: jobs that already exist get an empty prompt instead of nothing
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prompt', sa.Text(), server_default='', nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('prompt')

