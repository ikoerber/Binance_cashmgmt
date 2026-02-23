"""remove xrpbtc cross pair columns

Revision ID: 094dac6f695a
Revises: a7b8c9d0e1f2
Create Date: 2026-02-23 23:46:28.132957

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '094dac6f695a'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove cross-pair columns after XRPBTC removal."""
    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.drop_column('routing_decision_json')
        batch_op.drop_column('base_asset')

    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')

    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.drop_column('cost_eur')
        batch_op.drop_column('lot_symbol')

    with op.batch_alter_table('sell_allocations', schema=None) as batch_op:
        batch_op.drop_column('realized_pnl_eur')


def downgrade() -> None:
    """Re-add cross-pair columns (rollback)."""
    with op.batch_alter_table('sell_allocations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('realized_pnl_eur', sa.Numeric(), nullable=True))

    with op.batch_alter_table('pairing_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lot_symbol', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('cost_eur', sa.Numeric(), nullable=True))

    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('quote_to_eur_rate', sa.Numeric(), nullable=True))

    with op.batch_alter_table('pairings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('base_asset', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('routing_decision_json', sa.Text(), nullable=True))
