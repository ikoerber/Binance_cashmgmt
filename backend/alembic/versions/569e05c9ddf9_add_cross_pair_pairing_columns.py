"""add_cross_pair_pairing_columns

Revision ID: 569e05c9ddf9
Revises: f0f489761dc8
Create Date: 2026-02-20 18:44:21.972429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '569e05c9ddf9'
down_revision: Union[str, Sequence[str], None] = 'f0f489761dc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add base_asset to pairings, cost_eur + lot_symbol to pairing_items."""
    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_asset', sa.String(), nullable=True))

    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cost_eur', sa.Numeric(precision=20, scale=10), nullable=True))
        batch_op.add_column(sa.Column('lot_symbol', sa.String(), nullable=True))


def downgrade() -> None:
    """Drop cross-pair pairing columns."""
    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.drop_column('lot_symbol')
        batch_op.drop_column('cost_eur')

    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.drop_column('base_asset')
