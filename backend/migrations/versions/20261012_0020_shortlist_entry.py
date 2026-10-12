"""The shortlist: table shortlist_entry, the included candidates chosen for the interview invitation.

One row per candidate (candidate_id is unique): job_id, candidate_id, rule ("Top 5", "Final score at least 70",
"Added by hand"), added_by (the interviewer's email) and added_at.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-12 12:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('shortlist_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('rule', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('added_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('added_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('shortlist_entry', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shortlist_entry_candidate_id'), ['candidate_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_shortlist_entry_job_id'), ['job_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('shortlist_entry', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shortlist_entry_job_id'))
        batch_op.drop_index(batch_op.f('ix_shortlist_entry_candidate_id'))

    op.drop_table('shortlist_entry')
