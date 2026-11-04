"""Card type and last 4 digits on accounts (Mini App)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-04 23:50:00.000000
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FOUR_DIGITS = re.compile(r"(?<!\d)\d{4}(?!\d)")


def upgrade() -> None:
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        # cash | uzcard | humo | visa | mastercard; NULL for accounts created before the Mini App
        batch_op.add_column(sa.Column('card_type', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('last4', sa.String(length=4), nullable=True))

    # Accounts named like "UOB 4417" (the old way of teaching the bot the card digits) get last4 filled in
    connection = op.get_bind()
    accounts = sa.table('accounts', sa.column('id', sa.Integer), sa.column('name', sa.String),
                        sa.column('kind', sa.String), sa.column('last4', sa.String))
    for account_id, name, kind in connection.execute(sa.select(accounts.c.id, accounts.c.name, accounts.c.kind)):
        found = _FOUR_DIGITS.findall(name or "")
        if kind != 'cash' and len(found) == 1:
            connection.execute(accounts.update().where(accounts.c.id == account_id).values(last4=found[0]))


def downgrade() -> None:
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('last4')
        batch_op.drop_column('card_type')
