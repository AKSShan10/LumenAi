"""Applications are read from the job's Google Form (Google Forms API), not from a response sheet.

job.response_sheet_url  removed: no sheet link is needed any more
job.google_form_link    the form link (the "Apply now" link of the job post) the form id was found for
job.google_form_id      the form's own id, found once and kept
job.sheet_checkpoint_row -> job.form_checkpoint_row  (the same number: the last answer row that is finished)

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-09 15:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('google_form_link', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('google_form_id', sa.String(), nullable=False, server_default=''))
        batch_op.alter_column('sheet_checkpoint_row', new_column_name='form_checkpoint_row')
        batch_op.drop_column('response_sheet_url')


def downgrade() -> None:
    with op.batch_alter_table('job', schema=None) as batch_op:
        batch_op.add_column(sa.Column('response_sheet_url', sa.String(), nullable=False, server_default=''))
        batch_op.alter_column('form_checkpoint_row', new_column_name='sheet_checkpoint_row')
        batch_op.drop_column('google_form_id')
        batch_op.drop_column('google_form_link')
