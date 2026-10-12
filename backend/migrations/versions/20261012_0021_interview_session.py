"""Interviews: table interview_session, one scheduled video interview of a shortlisted candidate with its invitation.

join_token (unique) makes the candidate's private link APP_URL/join/<join_token>; room_name (unique) names the video
room. invitation_status: "" (draft) | sent | not_sent | no_email | failed: <reason>. calendar_sequence goes up when the
time changes, so the candidate's calendar updates the same event.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-12 15:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('interview_session',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('scheduled_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('duration_minutes', sa.Integer(), nullable=False),
    sa.Column('time_zone', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('join_token', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('room_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('calendar_sequence', sa.Integer(), nullable=False),
    sa.Column('invite_email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('invitation_subject', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('invitation_body', sa.Text(), nullable=True),
    sa.Column('invitation_status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('sent_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_interview_session_candidate_id'), ['candidate_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_interview_session_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_interview_session_join_token'), ['join_token'], unique=True)
        batch_op.create_index(batch_op.f('ix_interview_session_room_name'), ['room_name'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_interview_session_room_name'))
        batch_op.drop_index(batch_op.f('ix_interview_session_join_token'))
        batch_op.drop_index(batch_op.f('ix_interview_session_job_id'))
        batch_op.drop_index(batch_op.f('ix_interview_session_candidate_id'))

    op.drop_table('interview_session')
