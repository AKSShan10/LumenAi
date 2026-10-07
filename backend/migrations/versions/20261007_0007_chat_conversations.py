"""Chat conversations: "New chat" keeps the earlier chats instead of deleting them.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07 10:30:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('chat_conversation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chat_message', schema=None) as batch_op:
        batch_op.add_column(sa.Column('conversation_id', sa.Integer(), server_default='0', nullable=False))
        batch_op.create_index(batch_op.f('ix_chat_message_conversation_id'), ['conversation_id'], unique=False)

    # The messages that are already there become the first chat, so nothing is lost.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM chat_message")).scalar():
        connection.execute(sa.text("INSERT INTO chat_conversation (created_at) VALUES (CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("UPDATE chat_message SET conversation_id = (SELECT MAX(id) FROM chat_conversation)"))


def downgrade() -> None:
    with op.batch_alter_table('chat_message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_chat_message_conversation_id'))
        batch_op.drop_column('conversation_id')
    op.drop_table('chat_conversation')
