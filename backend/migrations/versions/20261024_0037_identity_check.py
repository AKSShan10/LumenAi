"""Candidate identification (F7): the photo and the face vector of a candidate, and the identity
check of an interview.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-24 10:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('photo_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('face_vector', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('face_status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))

    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.add_column(sa.Column('identity', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('interview_session', schema=None) as batch_op:
        batch_op.drop_column('identity')

    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.drop_column('face_status')
        batch_op.drop_column('face_vector')
        batch_op.drop_column('photo_path')
