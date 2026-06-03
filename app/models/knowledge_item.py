from sqlalchemy import Column, BigInteger, String, Text, DateTime, ForeignKey, JSON, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
    _HAS_PGVECTOR = True
except ImportError:
    _HAS_PGVECTOR = False
    Vector = None


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)         # AI-generated summary
    item_type = Column(String(32), default="note")
    # item_type: note | document | idea | research | meeting | email | pdf | webpage
    source = Column(String(512), nullable=True)   # URL, filename, etc.
    tags = Column(JSON, default=list)
    is_active = Column(Boolean, default=True, index=True)
    # Vector embedding for semantic search — populated async after creation
    embedding = Column(Vector(1536) if _HAS_PGVECTOR and Vector else Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
