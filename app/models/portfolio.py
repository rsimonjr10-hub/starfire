from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class PortfolioState(Base):
    __tablename__ = "portfolio_state"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    total_value = Column(Numeric(18, 4), default=0)
    cash = Column(Numeric(18, 4), default=0)
    positions = Column(JSON, default=dict)
    daily_pnl = Column(Numeric(18, 4), default=0)
    daily_pnl_pct = Column(Numeric(8, 4), default=0)
    snapshot_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
