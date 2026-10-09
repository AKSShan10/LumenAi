"""Job table: one job opening with its requirements and its description.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 10:00:05.384496
"""
import sqlalchemy as sa
import sqlmodel
from alembic import op


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('job',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('required_skills', sa.JSON(), nullable=True),
    sa.Column('preferred_skills', sa.JSON(), nullable=True),
    sa.Column('min_years', sa.Integer(), nullable=False),
    sa.Column('qualifications', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('approved_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('job')
