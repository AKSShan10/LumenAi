"""LangGraph memory for the assistant chat.

chat_conversation.agent_thread:  the thread id of this chat in LangGraph's checkpointer ("" = none yet)
chat_conversation.agent_seen_id: the id of the last chat_message the agent already has in that thread,
                                 so only newer lines are given to it

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-09 12:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('chat_conversation', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_thread', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('agent_seen_id', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('chat_conversation', schema=None) as batch_op:
        batch_op.drop_column('agent_seen_id')
        batch_op.drop_column('agent_thread')
