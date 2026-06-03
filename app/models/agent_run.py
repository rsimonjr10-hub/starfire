from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, JSON, Numeric
from sqlalchemy.sql import func
from app.database import Base


class AgentRun(Base):
    """Records every agent execution for observability and replay."""
    __tablename__ = "agent_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False, index=True)
    # agent_name: cfo | research | scheduler | investment | health | operations | ceo
    trigger = Column(String(64), nullable=True)         # manual | schedule | automation | event
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    report_text = Column(Text, nullable=True)           # human-readable output
    status = Column(String(32), default="running")      # running | completed | failed
    duration_ms = Column(BigInteger, nullable=True)
    tokens_used = Column(BigInteger, nullable=True)
    cost_usd = Column(Numeric(10, 6), nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
