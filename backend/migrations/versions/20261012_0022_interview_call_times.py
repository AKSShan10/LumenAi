"""The session record of the video call: when the interviewer started it, when the candidate first joined,
and when it ended (interview_session.started_at, candidate_joined_at, ended_at).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-12 18:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('started_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('candidate_joined_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('ended_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.drop_column('ended_at')
        batch_op.drop_column('candidate_joined_at')
        batch_op.drop_column('started_at')
