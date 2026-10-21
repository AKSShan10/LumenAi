"""Assessment weight per job: job.assessment_cv_weight (the CV part of the overall score in %; empty = 40).

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-21 12:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assessment_cv_weight', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('assessment_cv_weight')
