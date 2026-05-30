"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("first_name", sa.String(256), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("preferences", sa.JSON(), nullable=True),
        sa.Column("conversation_history", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])

    op.create_table(
        "portfolio_state",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("total_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("cash", sa.Numeric(18, 4), nullable=True),
        sa.Column("positions", sa.JSON(), nullable=True),
        sa.Column("daily_pnl", sa.Numeric(18, 4), nullable=True),
        sa.Column("daily_pnl_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_portfolio_state_user_id", "portfolio_state", ["user_id"])

    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("size_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=True),
        sa.Column("requested_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("filled_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("slippage", sa.Numeric(8, 6), nullable=True),
        sa.Column("status", sa.String(20), default="PENDING"),
        sa.Column("block_reason", sa.String(512), nullable=True),
        sa.Column("broker_order_id", sa.String(128), nullable=True),
        sa.Column("intent_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trades_user_id", "trades", ["user_id"])

    op.create_table(
        "spending_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(8), default="USD"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_spending_records_user_id", "spending_records", ["user_id"])

    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.String(2048), nullable=True),
        sa.Column("priority", sa.Integer(), default=5),
        sa.Column("status", sa.String(20), default="PENDING"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])

    op.create_table(
        "goals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.String(2048), nullable=True),
        sa.Column("goal_type", sa.String(64), nullable=False),
        sa.Column("target_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("current_value", sa.Numeric(18, 4), default=0),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("status", sa.String(20), default="ACTIVE"),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])

    op.create_table(
        "event_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("processed", sa.String(8), default="NO"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_log_event_type", "event_log", ["event_type"])

    op.create_table(
        "execution_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trade_id", sa.BigInteger(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_logs_trade_id", "execution_logs", ["trade_id"])
    op.create_index("ix_execution_logs_user_id", "execution_logs", ["user_id"])


def downgrade() -> None:
    op.drop_table("execution_logs")
    op.drop_table("event_log")
    op.drop_table("goals")
    op.drop_table("tasks")
    op.drop_table("spending_records")
    op.drop_table("trades")
    op.drop_table("portfolio_state")
    op.drop_table("users")
