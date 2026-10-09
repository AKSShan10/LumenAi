"""Candidate table (applications and their saved CV files) and the response sheet link of a job.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07 15:37:52.188155
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A database that once ran an early version of this feature may still hold its old, unused table and column.
    existing = sa.inspect(op.get_bind())
    if 'candidate' in existing.get_table_names():
        op.drop_table('candidate')
    has_sheet_column = 'response_sheet_url' in [column['name'] for column in existing.get_columns('job')]

    op.create_table('candidate',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('applied_at', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('source_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('drive_file_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('original_file_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('file_path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('cv_text', sa.Text(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('warnings', sa.JSON(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_candidate_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_candidate_source_key'), ['source_key'], unique=False)

    # server_default: jobs that already exist get an empty link instead of nothing
    if not has_sheet_column:
        with op.batch_alter_table('job', schema=None) as batch_op:
            batch_op.add_column(sa.Column('response_sheet_url', sqlmodel.sql.sqltypes.AutoString(), server_default='', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.drop_column('response_sheet_url')

    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_candidate_source_key'))
        batch_op.drop_index(batch_op.f('ix_candidate_job_id'))

    op.drop_table('candidate')
