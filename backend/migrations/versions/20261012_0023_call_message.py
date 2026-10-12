"""The chat inside the video call: table call_message (interview, sender interviewer | candidate, text, time).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-12 20:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('call_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('sender', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('sent_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('call_message', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_call_message_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('call_message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_call_message_session_id'))
    op.drop_table('call_message')
