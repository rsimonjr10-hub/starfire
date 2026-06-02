"""
RAG (Retrieval-Augmented Generation) service.

Stores knowledge items with vector embeddings and retrieves semantically
similar items for injecting into LLM context.
"""
from typing import Optional

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_item import KnowledgeItem
from app.services.embeddings import embed

logger = structlog.get_logger(__name__)


async def upsert_embedding(db: AsyncSession, item: KnowledgeItem) -> None:
    """Compute and store the embedding for a knowledge item."""
    vec = await embed(f"{item.title}\n\n{item.content}")
    if vec is not None:
        item.embedding = vec
        await db.flush()


async def search(
    db: AsyncSession,
    user_id: int,
    query: str,
    limit: int = 5,
    item_type: Optional[str] = None,
) -> list[KnowledgeItem]:
    """
    Semantic search over user's knowledge base.
    Falls back to full-text ILIKE search when embeddings unavailable.
    """
    vec = await embed(query)

    if vec is not None:
        # pgvector cosine similarity search
        try:
            vec_str = "[" + ",".join(str(v) for v in vec) + "]"
            type_filter = "AND item_type = :itype" if item_type else ""
            sql = text(f"""
                SELECT id FROM knowledge_items
                WHERE user_id = :uid AND is_active = true {type_filter}
                ORDER BY embedding <=> :vec
                LIMIT :lim
            """)
            params = {"uid": user_id, "vec": vec_str, "lim": limit}
            if item_type:
                params["itype"] = item_type
            result = await db.execute(sql, params)
            ids = [row[0] for row in result.fetchall()]
            if ids:
                items = await db.execute(
                    select(KnowledgeItem).where(KnowledgeItem.id.in_(ids))
                )
                return items.scalars().all()
        except Exception as e:
            logger.warning("pgvector_search_failed", error=str(e))

    # Fallback: full-text search
    q = select(KnowledgeItem).where(
        KnowledgeItem.user_id == user_id,
        KnowledgeItem.is_active == True,
        (KnowledgeItem.content.ilike(f"%{query}%") |
         KnowledgeItem.title.ilike(f"%{query}%")),
    ).limit(limit)
    if item_type:
        q = q.where(KnowledgeItem.item_type == item_type)
    result = await db.execute(q)
    return result.scalars().all()


async def build_rag_context(
    db: AsyncSession,
    user_id: int,
    query: str,
    max_chars: int = 4000,
) -> str:
    """Return a formatted context block of relevant knowledge for LLM injection."""
    items = await search(db, user_id, query, limit=6)
    if not items:
        return ""
    lines = ["## Relevant Knowledge"]
    chars = 0
    for item in items:
        entry = f"\n### {item.title} ({item.item_type})\n{item.content}"
        if chars + len(entry) > max_chars:
            break
        lines.append(entry)
        chars += len(entry)
    return "\n".join(lines)
