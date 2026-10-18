"""Consolidated assessment (F6): table assessment (one per candidate).

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-18 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('assessment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('cv_score', sa.Float(), nullable=True),
    sa.Column('interview_score', sa.Float(), nullable=True),
    sa.Column('cv_weight', sa.Integer(), nullable=False),
    sa.Column('overall_score', sa.Float(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('strengths', sa.JSON(), nullable=True),
    sa.Column('weaknesses', sa.JSON(), nullable=True),
    sa.Column('evidence_gaps', sa.JSON(), nullable=True),
    sa.Column('recommended_areas', sa.JSON(), nullable=True),
    sa.Column('repair_rounds', sa.Integer(), nullable=False),
    sa.Column('decision', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('decided_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('decided_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('assessment', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_assessment_candidate_id'), ['candidate_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_assessment_job_id'), ['job_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('assessment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_assessment_job_id'))
        batch_op.drop_index(batch_op.f('ix_assessment_candidate_id'))
    op.drop_table('assessment')
