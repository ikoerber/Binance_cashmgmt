"""Add fee_eur_value to ledger_events

Revision ID: 56a67fbefa2b
Revises: b3f7e2a1d456
Create Date: 2026-02-15 23:59:01.973019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56a67fbefa2b'
down_revision: Union[str, Sequence[str], None] = 'b3f7e2a1d456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ledger_events', sa.Column('fee_eur_value', sa.Numeric(precision=20, scale=10), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ledger_events', 'fee_eur_value')
