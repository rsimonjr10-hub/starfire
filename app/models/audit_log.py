from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(128), nullable=False, index=True)
    # e.g. memory.create, goal.update, invoice.delete, agent.run
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(BigInteger, nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
