"""First tables: workflow_run (module 2) and company_document (company documents for RAG).

Revision ID: 0001
Revises: 
Create Date: 2026-10-06 08:23:34.602732
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('company_document',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('source', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('embedding', sa.JSON(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('company_document', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_company_document_job_id'), ['job_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_company_document_kind'), ['kind'], unique=False)

    op.create_table('workflow_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stage', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('outcome', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('seconds', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('workflow_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_workflow_run_stage'), ['stage'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('workflow_run', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workflow_run_stage'))

    op.drop_table('workflow_run')
    with op.batch_alter_table('company_document', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_company_document_kind'))
        batch_op.drop_index(batch_op.f('ix_company_document_job_id'))

    op.drop_table('company_document')
