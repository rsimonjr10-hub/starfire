from sqlalchemy import Column, BigInteger, String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class UserMemory(Base):
    __tablename__ = "user_memories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(32), default="fact")   # fact | preference | instruction | event
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=5)          # 1-10
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
