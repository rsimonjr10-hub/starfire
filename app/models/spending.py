from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class SpendingRecord(Base):
    __tablename__ = "spending_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(8), default="USD")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
