"""Candidate scoring (F4): the job's weights and each candidate's section scores and weighted score.

job.weight_skills / weight_experience / weight_qualifications: how much each section counts (they add up to 100);
existing jobs get 50 / 30 / 20.
screening_result.sections: per section the AI's score (0-100), reason and checked quote.
screening_result.weighted_score: the sections combined with the job's weights (calculated by Python).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-08 12:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('weight_skills', sa.Integer(), nullable=False, server_default='50'))
        batch_op.add_column(sa.Column('weight_experience', sa.Integer(), nullable=False, server_default='30'))
        batch_op.add_column(sa.Column('weight_qualifications', sa.Integer(), nullable=False, server_default='20'))

    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sections', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('weighted_score', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.drop_column('weighted_score')
        batch_op.drop_column('sections')

    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('weight_qualifications')
        batch_op.drop_column('weight_experience')
        batch_op.drop_column('weight_skills')
