"""Add google_token_json and budget_json to users

Revision ID: 002
Revises: 001
Create Date: 2026-05-30 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_token_json", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("budget_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "budget_json")
    op.drop_column("users", "google_token_json")
