from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, JSON, Text
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    first_name = Column(String(256), nullable=True)
    is_active = Column(Boolean, default=True)
    preferences = Column(JSON, default=dict)
    conversation_history = Column(JSON, default=list)
    google_token_json = Column(Text, nullable=True)   # OAuth2 token JSON
    budget_json = Column(JSON, nullable=True)          # {category: monthly_limit}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
