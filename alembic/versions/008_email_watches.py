"""Email watch alerts

Revision ID: 008
Revises: 007
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_watches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("query", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_subject", sa.String(512), nullable=True),
        sa.Column("matched_from", sa.String(256), nullable=True),
    )


def downgrade():
    op.drop_table("email_watches")
