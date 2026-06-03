from sqlalchemy import Column, BigInteger, Numeric, DateTime, ForeignKey, JSON, Date
from sqlalchemy.sql import func
from app.database import Base


class NetWorthSnapshot(Base):
    """Daily snapshot of the user's complete balance sheet."""
    __tablename__ = "net_worth_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)

    # Assets
    cash = Column(Numeric(18, 2), default=0)
    investments = Column(Numeric(18, 2), default=0)    # brokerage + retirement
    real_estate = Column(Numeric(18, 2), default=0)
    business_value = Column(Numeric(18, 2), default=0)
    crypto = Column(Numeric(18, 2), default=0)
    other_assets = Column(Numeric(18, 2), default=0)
    total_assets = Column(Numeric(18, 2), default=0)

    # Liabilities
    credit_cards = Column(Numeric(18, 2), default=0)
    loans = Column(Numeric(18, 2), default=0)
    mortgage = Column(Numeric(18, 2), default=0)
    other_liabilities = Column(Numeric(18, 2), default=0)
    total_liabilities = Column(Numeric(18, 2), default=0)

    # Net
    net_worth = Column(Numeric(18, 2), default=0)

    # Income / expenses that month
    income_mtd = Column(Numeric(18, 2), default=0)
    expenses_mtd = Column(Numeric(18, 2), default=0)
    savings_rate = Column(Numeric(8, 4), default=0)    # percentage

    # Source breakdown (JSON for flexible account list)
    breakdown = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
