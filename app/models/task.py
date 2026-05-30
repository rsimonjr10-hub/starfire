from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(String(2048), nullable=True)
    priority = Column(Integer, default=5)
    status = Column(String(20), default="PENDING")   # PENDING | IN_PROGRESS | DONE | CANCELLED
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
