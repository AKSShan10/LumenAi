"""Talent pool (innovation feature): tables talent_pool and talent_invite.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-22 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('talent_invite',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pool_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('subject', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('sent_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('sent_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('talent_invite', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_talent_invite_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_talent_invite_pool_id'), ['pool_id'], unique=False)

    op.create_table('talent_pool',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('added_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('added_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('keep_until', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('unsubscribe_token', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('unsubscribed_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('talent_pool', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_talent_pool_candidate_id'), ['candidate_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_talent_pool_unsubscribe_token'), ['unsubscribe_token'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('talent_pool', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_talent_pool_unsubscribe_token'))
        batch_op.drop_index(batch_op.f('ix_talent_pool_candidate_id'))

    op.drop_table('talent_pool')
    with op.batch_alter_table('talent_invite', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_talent_invite_pool_id'))
        batch_op.drop_index(batch_op.f('ix_talent_invite_job_id'))

    op.drop_table('talent_invite')
