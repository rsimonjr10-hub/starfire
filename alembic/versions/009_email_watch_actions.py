"""Email watch on_match actions

Revision ID: 009
Revises: 008
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_watches",
        sa.Column("on_match", sa.String(32), nullable=False, server_default="notify"),
    )
    op.add_column(
        "email_watches",
        sa.Column("label_name", sa.String(128), nullable=True),
    )


def downgrade():
    op.drop_column("email_watches", "label_name")
    op.drop_column("email_watches", "on_match")
