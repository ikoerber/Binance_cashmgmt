"""readd quote_to_eur_rate for v3.0

Revision ID: b2f6ed7bb098
Revises: 094dac6f695a
Create Date: 2026-02-25 21:51:33.989709

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f6ed7bb098'
down_revision: Union[str, Sequence[str], None] = '094dac6f695a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Re-add quote_to_eur_rate on trade_lots for v3.0 XRPBTC support.

    Reverse of 094dac6f695a (partial): only re-adds quote_to_eur_rate on trade_lots.
    Pairing columns not needed (pairing disabled for BTC-quoted pairs per user decision).
    """
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('quote_to_eur_rate', sa.Numeric(precision=20, scale=10), nullable=True)
        )

    # Backfill EUR-quoted lots: rate = 1.0 (cost_eur already equals cost_quote)
    op.execute(sa.text("""
        UPDATE trade_lots
        SET quote_to_eur_rate = 1.0
        WHERE symbol IN ('BTCEUR', 'ETHEUR', 'XRPEUR')
          AND quote_to_eur_rate IS NULL
    """))


def downgrade() -> None:
    """Remove quote_to_eur_rate from trade_lots."""
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')
