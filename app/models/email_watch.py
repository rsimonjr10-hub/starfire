from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class EmailWatch(Base):
    __tablename__ = "email_watches"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(String(512), nullable=False)   # human-readable label
    query = Column(String(512), nullable=False)          # Gmail search query
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    found_at = Column(DateTime(timezone=True), nullable=True)
    matched_subject = Column(String(512), nullable=True)
    matched_from = Column(String(256), nullable=True)
