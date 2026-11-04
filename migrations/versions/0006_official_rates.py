"""Official USD rate (Central Bank of Uzbekistan) and reset of manual rates

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'official_rates',
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('rate', sa.String(), nullable=False),
        sa.Column('rate_date', sa.Date(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('currency'),
    )
    # Manual rates may hold wrong values; from now on the official rate is the default for everyone
    # (a user can set an override again with /rate 1 USD <rate> UZS)
    op.execute("DELETE FROM exchange_rates")


def downgrade() -> None:
    op.drop_table('official_rates')
