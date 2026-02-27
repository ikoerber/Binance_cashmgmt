"""Add dry-run tables and settings column

Revision ID: dr01_dry_run_tab
Revises: 061714dcd26c
Create Date: 2026-02-27 16:10:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "dr01_dry_run_tab"
down_revision = "061714dcd26c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create dry_run_decisions table
    op.create_table(
        "dry_run_decisions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("alpha_score", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("trade_signal", sa.String(), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("quality", sa.String(), nullable=False),
        sa.Column("factor_zscore", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("factor_leadlag", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column(
            "factor_imbalance",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
        ),
        sa.Column("factor_funding", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("factors_json", sa.JSON(), nullable=False),
        sa.Column(
            "current_price",
            sa.Numeric(precision=20, scale=10),
            nullable=False,
        ),
        sa.Column(
            "trailing_stop_level",
            sa.Numeric(precision=20, scale=10),
            nullable=True,
        ),
        sa.Column("regime_label", sa.String(), nullable=True),
        sa.Column("regime_hurst", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("virtual_qty", sa.Numeric(precision=20, scale=10), nullable=True),
        sa.Column("virtual_price", sa.Numeric(precision=20, scale=10), nullable=True),
        sa.Column("virtual_fee", sa.Numeric(precision=20, scale=10), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_drd_user_symbol_time",
        "dry_run_decisions",
        ["user_id", "symbol", "evaluated_at"],
    )
    op.create_index(
        "idx_drd_user_action",
        "dry_run_decisions",
        ["user_id", "action"],
    )
    op.create_index(
        op.f("ix_dry_run_decisions_evaluated_at"),
        "dry_run_decisions",
        ["evaluated_at"],
    )

    # 2. Create dry_run_portfolios table
    op.create_table(
        "dry_run_portfolios",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column(
            "initial_capital",
            sa.Numeric(precision=20, scale=2),
            nullable=False,
        ),
        sa.Column("cash", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("total_equity", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column(
            "unrealized_pnl",
            sa.Numeric(precision=20, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "realized_pnl",
            sa.Numeric(precision=20, scale=4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "trade_count",
            sa.Numeric(precision=10, scale=0),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "win_count",
            sa.Numeric(precision=10, scale=0),
            nullable=False,
            server_default="0",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    # 3. Create dry_run_positions table
    op.create_table(
        "dry_run_positions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("portfolio_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("qty", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("entry_time", sa.DateTime(), nullable=False),
        sa.Column("fees_paid", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("decision_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["portfolio_id"], ["dry_run_portfolios.id"]),
        sa.ForeignKeyConstraint(["decision_id"], ["dry_run_decisions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_drp_user_symbol",
        "dry_run_positions",
        ["user_id", "symbol"],
    )

    # 4. Add dry_run_initial_capital to user_settings (batch mode for SQLite)
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "dry_run_initial_capital",
                sa.Numeric(precision=20, scale=2),
                nullable=True,
            )
        )


def downgrade() -> None:
    # Remove column from user_settings (batch mode for SQLite)
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("dry_run_initial_capital")

    # Drop tables in reverse order (positions first due to FK)
    op.drop_index("idx_drp_user_symbol", table_name="dry_run_positions")
    op.drop_table("dry_run_positions")

    op.drop_table("dry_run_portfolios")

    op.drop_index(
        op.f("ix_dry_run_decisions_evaluated_at"),
        table_name="dry_run_decisions",
    )
    op.drop_index("idx_drd_user_action", table_name="dry_run_decisions")
    op.drop_index("idx_drd_user_symbol_time", table_name="dry_run_decisions")
    op.drop_table("dry_run_decisions")
