"""add_sell_allocation_strategy_to_settings

Revision ID: b3f7e2a1d456
Revises: a18b2129e148
Create Date: 2026-02-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7e2a1d456'
down_revision: Union[str, Sequence[str], None] = 'a18b2129e148'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_settings', sa.Column('sell_allocation_strategy', sa.String(), server_default='FIFO', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('user_settings', 'sell_allocation_strategy')
