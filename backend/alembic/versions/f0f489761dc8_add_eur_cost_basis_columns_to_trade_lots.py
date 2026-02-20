"""add EUR cost basis columns to trade_lots

Revision ID: f0f489761dc8
Revises: q1w2e3r4t5y6
Create Date: 2026-02-20 16:47:40.153602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0f489761dc8'
down_revision: Union[str, Sequence[str], None] = 'q1w2e3r4t5y6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add cost_eur and quote_to_eur_rate columns, backfill EUR-quoted lots."""
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cost_eur', sa.Numeric(precision=20, scale=10), nullable=True))
        batch_op.add_column(sa.Column('quote_to_eur_rate', sa.Numeric(precision=20, scale=10), nullable=True))

    # Backfill EUR-quoted lots: cost_eur = cost_quote, rate = 1.0
    op.execute(
        sa.text("""
            UPDATE trade_lots
            SET cost_eur = cost_quote,
                quote_to_eur_rate = 1.0
            WHERE symbol IN ('BTCEUR', 'ETHEUR', 'XRPEUR')
              AND cost_eur IS NULL
        """)
    )


def downgrade() -> None:
    """Drop cost_eur and quote_to_eur_rate columns."""
    with op.batch_alter_table('trade_lots', schema=None) as batch_op:
        batch_op.drop_column('quote_to_eur_rate')
        batch_op.drop_column('cost_eur')
