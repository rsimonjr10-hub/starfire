"""add snaptrade user fields

Revision ID: 006
Revises: 005
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("snaptrade_user_id", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("snaptrade_user_secret", sa.String(256), nullable=True))


def downgrade():
    op.drop_column("users", "snaptrade_user_secret")
    op.drop_column("users", "snaptrade_user_id")
