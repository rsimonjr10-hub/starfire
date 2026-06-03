from sqlalchemy import Column, BigInteger, String, Integer, Text, Date, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from app.database import Base


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    entry_date = Column(Date, nullable=False, index=True)
    content = Column(Text, nullable=False)
    mood = Column(Integer, nullable=True)        # 1-10
    energy = Column(Integer, nullable=True)      # 1-10
    gratitude = Column(Text, nullable=True)
    intentions = Column(Text, nullable=True)
    wins = Column(Text, nullable=True)
    challenges = Column(Text, nullable=True)
    tags = Column(JSON, default=list)            # ["work", "health", ...]
    ai_summary = Column(Text, nullable=True)     # AI-generated summary
    ai_insights = Column(Text, nullable=True)    # AI-generated insights
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
