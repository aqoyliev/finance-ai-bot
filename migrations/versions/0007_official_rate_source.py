"""Source of the stored default rate (cbu | market)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # existing rows came from the Central Bank
    with op.batch_alter_table('official_rates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(), nullable=False, server_default='cbu'))


def downgrade() -> None:
    with op.batch_alter_table('official_rates', schema=None) as batch_op:
        batch_op.drop_column('source')
