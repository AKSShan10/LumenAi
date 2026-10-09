"""Job posting table: each try to post an approved job to Telegram, and how it ended.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06 11:38:21.952610
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('job_posting',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('channel', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('apply_url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('message_id', sa.Integer(), nullable=False),
    sa.Column('message_link', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('job_posting', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_job_posting_job_id'), ['job_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('job_posting', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_job_posting_job_id'))

    op.drop_table('job_posting')
