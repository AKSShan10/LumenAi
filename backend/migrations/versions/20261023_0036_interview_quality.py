"""Interview quality assessment (F10): table interview_quality (one per interview).

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-23 20:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('interview_quality',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('quality_score', sa.Float(), nullable=True),
    sa.Column('scores', sa.JSON(), nullable=True),
    sa.Column('talk', sa.JSON(), nullable=True),
    sa.Column('coverage', sa.JSON(), nullable=True),
    sa.Column('questions', sa.JSON(), nullable=True),
    sa.Column('consistency', sa.JSON(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('recommendations', sa.JSON(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('interview_quality', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_interview_quality_session_id'), ['session_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('interview_quality', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interview_quality_session_id'))

    op.drop_table('interview_quality')
