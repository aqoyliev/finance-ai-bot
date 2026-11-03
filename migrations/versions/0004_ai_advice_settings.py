"""AI advice settings and last sent advice on users

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('advice_weekly', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('advice_monthly', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('advice_weekly_sent', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('advice_monthly_sent', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('advice_monthly_sent')
        batch_op.drop_column('advice_weekly_sent')
        batch_op.drop_column('advice_monthly')
        batch_op.drop_column('advice_weekly')
