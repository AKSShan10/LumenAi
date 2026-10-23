"""CV claim verification (F8): table claim_check (one per candidate).

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-23 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0034'
down_revision = '0033'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('claim_check',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('claims', sa.JSON(), nullable=True),
    sa.Column('updated_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('claim_check', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_claim_check_candidate_id'), ['candidate_id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('claim_check', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_claim_check_candidate_id'))

    op.drop_table('claim_check')
