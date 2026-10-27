"""Interview scorecard (F9): qa_analysis.scorecard and the qa_item grades problem_solving and depth.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-23 16:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('qa_analysis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scorecard', sa.JSON(), nullable=True))

    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('problem_solving', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('depth', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('qa_item', schema=None) as batch_op:
        batch_op.drop_column('depth')
        batch_op.drop_column('problem_solving')

    with op.batch_alter_table('qa_analysis', schema=None) as batch_op:
        batch_op.drop_column('scorecard')

