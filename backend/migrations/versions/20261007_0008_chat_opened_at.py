"""Chat conversations get "opened_at", so an earlier chat can be made the current one again.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07 13:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('chat_conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('opened_at', sqlmodel.sql.sqltypes.UTCDateTime(),
                                      server_default='2026-01-01 00:00:00', nullable=False))
    # The chats that are already there keep their order: opened when they were started.
    op.execute("UPDATE chat_conversation SET opened_at = created_at")


def downgrade() -> None:
    with op.batch_alter_table('chat_conversation', schema=None) as batch_op:
        batch_op.drop_column('opened_at')
