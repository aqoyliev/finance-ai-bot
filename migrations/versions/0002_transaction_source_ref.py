"""transaction source_ref for AI duplicate detection

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_ref', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_transactions_source_ref'), ['source_ref'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_source_ref'))
        batch_op.drop_column('source_ref')
