"""category budgets and sent limit alerts

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('budgets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'category')
    )
    op.create_index(op.f('ix_budgets_user_id'), 'budgets', ['user_id'], unique=False)
    op.create_table('alerts_sent',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('ref', sa.String(), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'kind', 'ref', 'threshold', 'period_start')
    )
    op.create_index(op.f('ix_alerts_sent_user_id'), 'alerts_sent', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_alerts_sent_user_id'), table_name='alerts_sent')
    op.drop_table('alerts_sent')
    op.drop_index(op.f('ix_budgets_user_id'), table_name='budgets')
    op.drop_table('budgets')
