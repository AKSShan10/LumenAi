"""Assistant chat tables: the conversation, and the questions that wait for a Yes or No.

Revision ID: 0006
Revises: 0004
Create Date: 2026-10-06 18:47:59.202448
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = '0006'
down_revision = '0004'      # 0005 (candidate table) was taken out again before it was committed
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assistant_action',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('job_title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('apply_url', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('chat_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('content', sa.Text(), nullable=True),
    sa.Column('tools', sa.JSON(), nullable=True),
    sa.Column('attachment_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('attachment_text', sa.Text(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('chat_message')
    op.drop_table('assistant_action')
