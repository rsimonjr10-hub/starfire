from sqlalchemy import Column, BigInteger, String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.database import Base


class BotTicket(Base):
    """A task STARFIRE delegates to another bot (OSIRIS, LUMISNOVA, etc.)."""
    __tablename__ = "bot_tickets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    assigned_to = Column(String(32), nullable=False)   # OSIRIS | LUMISNOVA | STARFIRE
    priority = Column(Integer, default=5)

    # QUEUED → SENT → ACKNOWLEDGED → DONE | FAILED
    status = Column(String(20), default="QUEUED", index=True)

    # Free-form data sent with the ticket (symbol, amounts, etc.)
    context = Column(JSONB, nullable=True)

    # When STARFIRE last asked the bot for a status update
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
