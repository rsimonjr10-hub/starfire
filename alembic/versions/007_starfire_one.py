"""Starfire One — new module tables

Revision ID: 007
Revises: 006
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector extension (no-op if not available)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # habits
    op.create_table(
        "habits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(16), default="daily"),
        sa.Column("target_count", sa.Integer(), default=1),
        sa.Column("current_streak", sa.Integer(), default=0),
        sa.Column("longest_streak", sa.Integer(), default=0),
        sa.Column("total_completions", sa.Integer(), default=0),
        sa.Column("last_completed_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("color", sa.String(16), default="#38bdf8"),
        sa.Column("icon", sa.String(8), default="⚡"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_habits_user_id", "habits", ["user_id"])

    # habit_logs
    op.create_table(
        "habit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("habit_id", sa.BigInteger(), sa.ForeignKey("habits.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("completed_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # journal_entries
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mood", sa.Integer(), nullable=True),
        sa.Column("energy", sa.Integer(), nullable=True),
        sa.Column("gratitude", sa.Text(), nullable=True),
        sa.Column("intentions", sa.Text(), nullable=True),
        sa.Column("wins", sa.Text(), nullable=True),
        sa.Column("challenges", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_insights", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_journal_user_id", "journal_entries", ["user_id"])
    op.create_index("ix_journal_entry_date", "journal_entries", ["entry_date"])

    # health_metrics
    op.create_table(
        "health_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("notes", sa.String(512), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_health_user_id", "health_metrics", ["user_id"])
    op.create_index("ix_health_metric_type", "health_metrics", ["metric_type"])

    # businesses
    op.create_table(
        "businesses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_type", sa.String(64), default="saas"),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("mrr", sa.Numeric(18, 2), default=0),
        sa.Column("arr", sa.Numeric(18, 2), default=0),
        sa.Column("total_revenue_mtd", sa.Numeric(18, 2), default=0),
        sa.Column("total_revenue_ytd", sa.Numeric(18, 2), default=0),
        sa.Column("customer_count", sa.BigInteger(), default=0),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_businesses_user_id", "businesses", ["user_id"])

    # customers
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("company", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("lifetime_value", sa.Numeric(18, 2), default=0),
        sa.Column("monthly_value", sa.Numeric(18, 2), default=0),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_customers_user_id", "customers", ["user_id"])

    # projects
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("business_id", sa.BigInteger(), sa.ForeignKey("businesses.id"), nullable=True),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), default="active"),
        sa.Column("priority", sa.BigInteger(), default=5),
        sa.Column("budget", sa.Numeric(18, 2), nullable=True),
        sa.Column("revenue", sa.Numeric(18, 2), default=0),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # invoices
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("customer_id", sa.BigInteger(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("invoice_number", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), default="draft"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 2), default=0),
        sa.Column("currency", sa.String(8), default="USD"),
        sa.Column("line_items", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("issue_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])

    # knowledge_items
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("item_type", sa.String(32), default="note"),
        sa.Column("source", sa.String(512), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("embedding", sa.Text(), nullable=True),  # fallback text if pgvector unavailable
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_knowledge_user_id", "knowledge_items", ["user_id"])
    op.create_index("ix_knowledge_is_active", "knowledge_items", ["is_active"])

    # Try to add proper vector column — only works if pgvector is installed
    try:
        op.execute("ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS embedding_vec vector(1536)")
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_embedding
            ON knowledge_items USING ivfflat (embedding_vec vector_cosine_ops)
            WITH (lists = 100)
        """)
    except Exception:
        pass  # pgvector not installed — falls back to text column + ILIKE search

    # automations
    op.create_table(
        "automations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("trigger_config", sa.JSON(), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_config", sa.JSON(), nullable=True),
        sa.Column("run_count", sa.BigInteger(), default=0),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"])

    # automation_runs
    op.create_table(
        "automation_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("automation_id", sa.BigInteger(), sa.ForeignKey("automations.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("triggered_by", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), default="success"),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.BigInteger(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_created_at", "audit_logs", ["created_at"])

    # net_worth_snapshots
    op.create_table(
        "net_worth_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("cash", sa.Numeric(18, 2), default=0),
        sa.Column("investments", sa.Numeric(18, 2), default=0),
        sa.Column("real_estate", sa.Numeric(18, 2), default=0),
        sa.Column("business_value", sa.Numeric(18, 2), default=0),
        sa.Column("crypto", sa.Numeric(18, 2), default=0),
        sa.Column("other_assets", sa.Numeric(18, 2), default=0),
        sa.Column("total_assets", sa.Numeric(18, 2), default=0),
        sa.Column("credit_cards", sa.Numeric(18, 2), default=0),
        sa.Column("loans", sa.Numeric(18, 2), default=0),
        sa.Column("mortgage", sa.Numeric(18, 2), default=0),
        sa.Column("other_liabilities", sa.Numeric(18, 2), default=0),
        sa.Column("total_liabilities", sa.Numeric(18, 2), default=0),
        sa.Column("net_worth", sa.Numeric(18, 2), default=0),
        sa.Column("income_mtd", sa.Numeric(18, 2), default=0),
        sa.Column("expenses_mtd", sa.Numeric(18, 2), default=0),
        sa.Column("savings_rate", sa.Numeric(8, 4), default=0),
        sa.Column("breakdown", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_nw_user_id", "net_worth_snapshots", ["user_id"])
    op.create_index("ix_nw_snapshot_date", "net_worth_snapshots", ["snapshot_date"])

    # agent_runs
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=True),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("report_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), default="running"),
        sa.Column("duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("tokens_used", sa.BigInteger(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])


def downgrade():
    for table in [
        "agent_runs", "net_worth_snapshots", "audit_logs",
        "automation_runs", "automations", "knowledge_items",
        "invoices", "projects", "customers", "businesses",
        "health_metrics", "journal_entries", "habit_logs", "habits",
    ]:
        op.drop_table(table)
