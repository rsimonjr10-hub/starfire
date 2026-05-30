from sqlalchemy import Column, BigInteger, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    source = Column(String(128), nullable=True)
    payload = Column(JSON, default=dict)
    processed = Column(String(8), default="NO")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    trade_id = Column(BigInteger, ForeignKey("trades.id"), nullable=True, index=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    action = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False)
    details = Column(JSON, default=dict)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
