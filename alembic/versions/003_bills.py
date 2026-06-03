"""Add bills table

Revision ID: 003
Revises: 002
Create Date: 2026-05-30 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("due_day", sa.BigInteger(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_recurring", sa.Boolean(), server_default="true"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("autopay", sa.Boolean(), server_default="false"),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("last_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bills_user_id", "bills", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_bills_user_id", table_name="bills")
    op.drop_table("bills")
