"""Candidate number inside each job (candidate.number): 1, 2, 3 ... for every job on its own.

Candidates that are already saved get their numbers here, per job, oldest first.
Their saved files keep their old names: the code finds a file by candidate.file_path, not by its name.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-08 10:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.add_column(sa.Column('number', sa.Integer(), nullable=False, server_default='0'))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, job_id FROM candidate ORDER BY job_id, id")).all()
    counted = {}
    for candidate_id, job_id in rows:
        counted[job_id] = counted.get(job_id, 0) + 1
        connection.execute(sa.text("UPDATE candidate SET number = :number WHERE id = :id"),
                           {"number": counted[job_id], "id": candidate_id})


def downgrade() -> None:
    with op.batch_alter_table('candidate', schema=None) as batch_op:
        batch_op.drop_column('number')
