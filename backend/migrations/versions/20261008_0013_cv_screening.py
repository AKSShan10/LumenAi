"""CV screening: table screening_result (one row per candidate), and where each CV text came from.

candidate.text_source: file (read by code) | ai_read (the AI read the PDF) | "" (no text)
candidate.read_problem: why the CV text may be incomplete ("" when it looks complete)
CVs that already have text are marked "file": they were read by code.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-08 10:38:59
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('screening_result',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('candidate_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=False),
    sa.Column('result', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('reason', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('parsed', sa.JSON(), nullable=True),
    sa.Column('matches', sa.JSON(), nullable=True),
    sa.Column('missing', sa.JSON(), nullable=True),
    sa.Column('model', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('screened_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_screening_result_candidate_id'), ['candidate_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_screening_result_job_id'), ['job_id'], unique=False)

    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('text_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('read_problem', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.execute("UPDATE candidate SET text_source = 'file' WHERE cv_text <> ''")


def downgrade() -> None:
    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.drop_column('read_problem')
        batch_op.drop_column('text_source')

    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_screening_result_job_id'))
        batch_op.drop_index(batch_op.f('ix_screening_result_candidate_id'))

    op.drop_table('screening_result')
