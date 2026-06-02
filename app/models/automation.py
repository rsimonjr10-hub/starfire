from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class Automation(Base):
    __tablename__ = "automations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, index=True)

    # Trigger definition
    trigger_type = Column(String(64), nullable=False)
    # trigger_type: spending_threshold | savings_rate_drop | goal_progress |
    #               schedule | net_worth_change | task_overdue | revenue_drop |
    #               habit_streak_broken | journal_missing
    trigger_config = Column(JSON, default=dict)
    # e.g. {"category": "food", "threshold": 500, "period": "monthly"}
    #      {"cron": "0 9 * * 1"}  (every Monday 9am)
    #      {"goal_id": 5, "at_pct": 100}

    # Action definition
    action_type = Column(String(64), nullable=False)
    # action_type: notify | create_task | generate_report | run_agent | send_briefing
    action_config = Column(JSON, default=dict)
    # e.g. {"message": "You exceeded your food budget!"}
    #      {"task_title": "Review spending", "priority": 8}

    run_count = Column(BigInteger, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AutomationRun(Base):
    __tablename__ = "automation_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    automation_id = Column(BigInteger, ForeignKey("automations.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    triggered_by = Column(String(64), nullable=True)  # scheduler | manual | event
    status = Column(String(32), default="success")    # success | failed | skipped
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    ran_at = Column(DateTime(timezone=True), server_default=func.now())
