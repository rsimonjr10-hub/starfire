from sqlalchemy import Column, BigInteger, String, Integer, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base


class Habit(Base):
    __tablename__ = "habits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    frequency = Column(String(16), default="daily")   # daily | weekly | monthly
    target_count = Column(Integer, default=1)          # times per period
    current_streak = Column(Integer, default=0)
    longest_streak = Column(Integer, default=0)
    total_completions = Column(Integer, default=0)
    last_completed_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)
    color = Column(String(16), default="#38bdf8")
    icon = Column(String(8), default="⚡")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class HabitLog(Base):
    __tablename__ = "habit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    habit_id = Column(BigInteger, ForeignKey("habits.id"), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    completed_date = Column(Date, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
