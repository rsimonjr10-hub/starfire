"""
Knowledge OS API — store notes, documents, and ideas with semantic search.
Auth: same HMAC dashboard token.
"""
import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.knowledge_item import KnowledgeItem
from app.services.rag import search, upsert_embedding
from app.services.embeddings import embed

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Auth (shared with dashboard) ───────────────────────────────────────────
def _make_token(telegram_id: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(telegram_id).encode(),
                    hashlib.sha256).hexdigest()[:32]


async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        for u in result.scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


# ── Schemas ────────────────────────────────────────────────────────────────
class KnowledgeCreate(BaseModel):
    title: str
    content: str
    item_type: str = "note"
    source: Optional[str] = None
    tags: list[str] = []


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    item_type: Optional[str] = None
    tags: Optional[list[str]] = None


# ── Endpoints ──────────────────────────────────────────────────────────────
@router.get("")
async def list_knowledge(
    item_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user: User = Depends(_get_user),
):
    async with AsyncSessionLocal() as session:
        q = select(KnowledgeItem).where(
            KnowledgeItem.user_id == user.id,
            KnowledgeItem.is_active == True,
        ).order_by(KnowledgeItem.created_at.desc()).limit(limit)
        if item_type:
            q = q.where(KnowledgeItem.item_type == item_type)
        items = (await session.execute(q)).scalars().all()
    return [_serialize(i) for i in items]


@router.post("")
async def create_knowledge(body: KnowledgeCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        item = KnowledgeItem(
            user_id=user.id,
            title=body.title,
            content=body.content,
            item_type=body.item_type,
            source=body.source,
            tags=body.tags,
        )
        session.add(item)
        await session.flush()
        await upsert_embedding(session, item)
        await session.commit()
        await session.refresh(item)
    return _serialize(item)


@router.get("/search")
async def search_knowledge(
    q: str = Query(..., min_length=2),
    item_type: Optional[str] = Query(None),
    limit: int = Query(10, le=50),
    user: User = Depends(_get_user),
):
    async with AsyncSessionLocal() as session:
        items = await search(session, user.id, q, limit=limit, item_type=item_type)
    return [_serialize(i) for i in items]


@router.get("/{item_id}")
async def get_knowledge(item_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        item = await _fetch(session, item_id, user.id)
    return _serialize(item)


@router.put("/{item_id}")
async def update_knowledge(item_id: int, body: KnowledgeUpdate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        item = await _fetch(session, item_id, user.id)
        if body.title is not None:
            item.title = body.title
        if body.content is not None:
            item.content = body.content
        if body.item_type is not None:
            item.item_type = body.item_type
        if body.tags is not None:
            item.tags = body.tags
        await upsert_embedding(session, item)
        await session.commit()
    return {"ok": True}


@router.delete("/{item_id}")
async def delete_knowledge(item_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        item = await _fetch(session, item_id, user.id)
        item.is_active = False
        await session.commit()
    return {"ok": True}


async def _fetch(session, item_id: int, user_id: int) -> KnowledgeItem:
    result = await session.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == item_id, KnowledgeItem.user_id == user_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def _serialize(i: KnowledgeItem) -> dict:
    return {
        "id": i.id,
        "title": i.title,
        "content": i.content[:500] + "..." if len(i.content) > 500 else i.content,
        "item_type": i.item_type,
        "source": i.source,
        "tags": i.tags or [],
        "summary": i.summary,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }
