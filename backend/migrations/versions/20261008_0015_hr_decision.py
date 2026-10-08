"""Human control of the screening: the interviewer's decision next to the system result.

screening_result.decision: included | excluded | "" (none: the system result counts)
screening_result.decision_note / decided_by / decided_at: the optional note, who decided and when
screening_result.stale: "Screen all again" was clicked; the CV waits for a new screening (decisions are kept)
screening_result.thread_id: the LangGraph run that waits in hr_review (LangGraph keeps it in its own tables)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-08 14:00:00
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('decision', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('decision_note', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('decided_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('decided_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
        batch_op.add_column(sa.Column('stale', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('thread_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''))


def downgrade() -> None:
    with op.batch_alter_table('screening_result', schema=None) as batch_op:
        batch_op.drop_column('thread_id')
        batch_op.drop_column('stale')
        batch_op.drop_column('decided_at')
        batch_op.drop_column('decided_by')
        batch_op.drop_column('decision_note')
        batch_op.drop_column('decision')
