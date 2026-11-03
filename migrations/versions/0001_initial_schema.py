"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-04 01:52:19.639139
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('language', sa.String(length=2), nullable=True),
    sa.Column('salary_day', sa.Integer(), nullable=False),
    sa.Column('base_currency', sa.String(length=3), nullable=False),
    sa.Column('is_seeded', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('balance_minor', sa.BigInteger(), nullable=False),
    sa.Column('opening_balance_minor', sa.BigInteger(), nullable=False),
    sa.Column('credit_limit_minor', sa.BigInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_accounts_user_id'), ['user_id'], unique=False)

    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'name', 'kind')
    )
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_categories_user_id'), ['user_id'], unique=False)

    op.create_table('exchange_rates',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('from_currency', sa.String(length=3), nullable=False),
    sa.Column('to_currency', sa.String(length=3), nullable=False),
    sa.Column('rate', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'from_currency', 'to_currency')
    )
    op.create_table('subcategories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('subcategories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subcategories_category_id'), ['category_id'], unique=False)

    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('group_id', sa.String(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('direction', sa.String(length=3), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('subcategory', sa.String(), nullable=True),
    sa.Column('note', sa.String(), nullable=True),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transactions_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transactions_group_id'), ['group_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_transactions_occurred_at'), ['occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_transactions_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transactions_user_id'))
        batch_op.drop_index(batch_op.f('ix_transactions_occurred_at'))
        batch_op.drop_index(batch_op.f('ix_transactions_group_id'))
        batch_op.drop_index(batch_op.f('ix_transactions_account_id'))

    op.drop_table('transactions')
    with op.batch_alter_table('subcategories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subcategories_category_id'))

    op.drop_table('subcategories')
    op.drop_table('exchange_rates')
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_categories_user_id'))

    op.drop_table('categories')
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_accounts_user_id'))

    op.drop_table('accounts')
    op.drop_table('users')
