"""add reconciliation_run and alert_event tables + recon tolerance settings

Revision ID: a7b8c9d0e1f2
Revises: ddedaa7263d8
Create Date: 2026-02-22 22:23:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "ddedaa7263d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists (idempotent migration support)."""
    conn = op.get_bind()
    insp = inspect(conn)
    return table_name in insp.get_table_names()


def _add_column_if_not_exists(table: str, column: sa.Column) -> None:
    """Add column only if it doesn't already exist (idempotent)."""
    conn = op.get_bind()
    insp = inspect(conn)
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _index_exists(index_name: str, table_name: str) -> bool:
    """Check if an index already exists."""
    conn = op.get_bind()
    insp = inspect(conn)
    existing = {idx["name"] for idx in insp.get_indexes(table_name)}
    return index_name in existing


def upgrade() -> None:
    """Create reconciliation_runs and alert_events tables, add recon tolerance columns to user_settings."""
    # 1. Create reconciliation_runs table
    if not _table_exists("reconciliation_runs"):
        op.create_table(
            "reconciliation_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("trigger", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("report_json", sa.JSON(), nullable=False),
            sa.Column(
                "has_discrepancies",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("idx_recon_runs_user_created", "reconciliation_runs"):
        op.create_index(
            "idx_recon_runs_user_created",
            "reconciliation_runs",
            ["user_id", "created_at"],
        )

    # 2. Create alert_events table
    if not _table_exists("alert_events"):
        op.create_table(
            "alert_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("reconciliation_run_id", sa.String(), nullable=True),
            sa.Column("alert_type", sa.String(), nullable=False),
            sa.Column("severity", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("details_json", sa.JSON(), nullable=True),
            sa.Column(
                "acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            ),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(
                ["reconciliation_run_id"], ["reconciliation_runs.id"]
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("idx_alerts_user_ack", "alert_events"):
        op.create_index(
            "idx_alerts_user_ack", "alert_events", ["user_id", "acknowledged"]
        )
    if not _index_exists("idx_alerts_user_created", "alert_events"):
        op.create_index(
            "idx_alerts_user_created", "alert_events", ["user_id", "created_at"]
        )

    # 3. Add recon tolerance columns to user_settings (idempotent)
    _add_column_if_not_exists(
        "user_settings",
        sa.Column(
            "recon_tolerance_base",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
        ),
    )
    _add_column_if_not_exists(
        "user_settings",
        sa.Column(
            "recon_tolerance_quote",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop reconciliation_runs and alert_events tables, remove recon tolerance columns."""
    # 1. Remove recon tolerance columns from user_settings
    with op.batch_alter_table("user_settings", schema=None) as batch_op:
        batch_op.drop_column("recon_tolerance_quote")
        batch_op.drop_column("recon_tolerance_base")

    # 2. Drop alert_events table (before reconciliation_runs due to FK)
    op.drop_index("idx_alerts_user_created", table_name="alert_events")
    op.drop_index("idx_alerts_user_ack", table_name="alert_events")
    op.drop_table("alert_events")

    # 3. Drop reconciliation_runs table
    op.drop_index("idx_recon_runs_user_created", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
