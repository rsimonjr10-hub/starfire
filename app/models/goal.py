from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    description = Column(String(2048), nullable=True)
    goal_type = Column(String(64), nullable=False)   # financial | productivity | spending
    target_value = Column(Numeric(18, 4), nullable=True)
    current_value = Column(Numeric(18, 4), default=0)
    unit = Column(String(32), nullable=True)
    status = Column(String(20), default="ACTIVE")    # ACTIVE | ACHIEVED | ABANDONED
    target_date = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
