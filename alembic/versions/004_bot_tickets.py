"""Add bot_tickets table

Revision ID: 004
Revises: 003
Create Date: 2026-05-31 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bot_tickets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5"),
        sa.Column("status", sa.String(20), server_default="QUEUED"),
        sa.Column("context", JSONB(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bot_tickets_user_id", "bot_tickets", ["user_id"])
    op.create_index("ix_bot_tickets_status", "bot_tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bot_tickets_status", table_name="bot_tickets")
    op.drop_index("ix_bot_tickets_user_id", table_name="bot_tickets")
    op.drop_table("bot_tickets")
