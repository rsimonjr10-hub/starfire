from sqlalchemy import Column, BigInteger, String, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Bill(Base):
    __tablename__ = "bills"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(256), nullable=False)          # "Netflix", "Car Insurance", "Rent"
    category = Column(String(64), nullable=False)       # subscription|insurance|rent|utility|loan|other
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), default="USD")
    due_day = Column(BigInteger, nullable=True)         # day-of-month (1-31), None = one-time
    due_date = Column(DateTime(timezone=True), nullable=True)  # for one-time bills
    is_recurring = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    autopay = Column(Boolean, default=False)
    notes = Column(String(512), nullable=True)
    last_paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
