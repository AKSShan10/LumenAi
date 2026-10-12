"""The call chat shows names: call_message.sender_name (the role stays in sender).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-12 22:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('call_message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sender_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('call_message', schema=None) as batch_op:
        batch_op.drop_column('sender_name')
