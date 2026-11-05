"""Role-based access: grants of regular users and visitors of the bot

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('access_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=True),
    sa.Column('username', sa.String(), nullable=True),
    sa.Column('display_name', sa.String(), nullable=False, server_default=''),
    sa.Column('added_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_access_grants_username'), 'access_grants', ['username'], unique=False)
    op.create_table('visitors',
    sa.Column('user_id', sa.BigInteger(), autoincrement=False, nullable=False),
    sa.Column('username', sa.String(), nullable=False, server_default=''),
    sa.Column('first_name', sa.String(), nullable=False, server_default=''),
    sa.Column('last_name', sa.String(), nullable=False, server_default=''),
    sa.Column('language_code', sa.String(), nullable=False, server_default=''),
    sa.Column('first_seen', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.Column('notified', sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_index(op.f('ix_visitors_last_seen'), 'visitors', ['last_seen'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_visitors_last_seen'), table_name='visitors')
    op.drop_table('visitors')
    op.drop_index(op.f('ix_access_grants_username'), table_name='access_grants')
    op.drop_table('access_grants')
