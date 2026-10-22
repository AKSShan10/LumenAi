"""The AI helper in the call: table helper_message (interview, role, kind, text, suggested questions).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-16 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('helper_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('questions', sa.JSON(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('helper_message', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_helper_message_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('helper_message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_helper_message_session_id'))
    op.drop_table('helper_message')
