"""Q&A analysis (F5): tables qa_analysis (one per interview) and qa_item (one per question and answer).

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-17 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('qa_analysis',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('interview_score', sa.Float(), nullable=True),
    sa.Column('covered', sa.JSON(), nullable=True),
    sa.Column('uncovered', sa.JSON(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('qa_analysis', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_qa_analysis_session_id'), ['session_id'], unique=True)

    op.create_table('qa_item',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('question', sa.Text(), nullable=True),
    sa.Column('answer', sa.Text(), nullable=True),
    sa.Column('job_related', sa.Boolean(), nullable=False),
    sa.Column('split_from_multi_part', sa.Boolean(), nullable=False),
    sa.Column('relevance', sa.Integer(), nullable=True),
    sa.Column('accuracy', sa.Integer(), nullable=True),
    sa.Column('completeness', sa.Integer(), nullable=True),
    sa.Column('articulation', sa.Integer(), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('reasons', sa.JSON(), nullable=True),
    sa.Column('evidence_quote', sa.Text(), nullable=True),
    sa.Column('evidence_time', sa.Float(), nullable=True),
    sa.Column('requirements', sa.JSON(), nullable=True),
    sa.Column('references', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_qa_item_session_id'), ['session_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_qa_item_session_id'))
    op.drop_table('qa_item')
    with op.batch_alter_table('qa_analysis', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_qa_analysis_session_id'))
    op.drop_table('qa_analysis')
