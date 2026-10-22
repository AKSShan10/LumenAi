"""The live transcript: table transcript_turn (interview, speaker, start/end seconds, text).

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-15 10:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('transcript_turn',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('speaker', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('start_sec', sa.Float(), nullable=False),
    sa.Column('end_sec', sa.Float(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transcript_turn', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transcript_turn_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('transcript_turn', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transcript_turn_session_id'))
    op.drop_table('transcript_turn')
