from sqlalchemy import Column, BigInteger, String, Numeric, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)          # BUY | SELL
    size_pct = Column(Numeric(8, 4), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=True)
    requested_price = Column(Numeric(18, 4), nullable=True)
    filled_price = Column(Numeric(18, 4), nullable=True)
    slippage = Column(Numeric(8, 6), nullable=True)
    status = Column(String(20), default="PENDING")    # PENDING | FILLED | REJECTED | BLOCKED
    block_reason = Column(String(512), nullable=True)
    broker_order_id = Column(String(128), nullable=True)
    intent_payload = Column(JSON, default=dict)
    result_payload = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)
