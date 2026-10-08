"""Semantic matching and the ATS match score.

job.ats_keywords: the keywords an ATS would look for in a CV for this job, made once by the AI
                  ({"source": fingerprint of the job text, "keywords": [...]})
screening_result.ats: {"score", "matched", "missing", "total"} - the job's keywords found in the CV
screening_result.ats_score: the ATS match score 0-100
(Met / Partially met / Unmet is kept inside screening_result.matches, which is JSON: no new column.)

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-08 18:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ats_keywords', sa.JSON(), nullable=True))
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ats', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('ats_score', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.drop_column('ats_score')
        batch_op.drop_column('ats')
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('ats_keywords')
