"""The screening keeps the text it used in its own table, so it never changes the candidate table.

screening_result.cv_text: the text the screening used (for a scanned PDF: what the AI read)
screening_result.text_source: file | ai_read | ""
screening_result.read_problem: why the text could not be used ("" = fine)
Results that already exist get the text and reading fields of their candidate.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-08 16:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cv_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('text_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('read_problem', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
    op.execute("UPDATE screening_result SET cv_text = (SELECT cv_text FROM candidate WHERE candidate.id = screening_result.candidate_id), "
               "text_source = COALESCE((SELECT text_source FROM candidate WHERE candidate.id = screening_result.candidate_id), ''), "
               "read_problem = COALESCE((SELECT read_problem FROM candidate WHERE candidate.id = screening_result.candidate_id), '')")


def downgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.drop_column('read_problem')
        batch_op.drop_column('text_source')
        batch_op.drop_column('cv_text')
