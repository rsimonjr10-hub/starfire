"""
Embedding service — converts text to 1536-dim vectors via OpenAI.
Falls back gracefully when OPENAI_API_KEY is not set.
"""
import json
from typing import Optional

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

EMBED_URL = "https://api.openai.com/v1/embeddings"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


async def embed(text: str) -> Optional[list[float]]:
    """Return a 1536-dim embedding vector for text, or None if unavailable."""
    if not settings.openai_api_key:
        return None
    text = text.strip()[:8000]  # hard cap
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                EMBED_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": EMBED_MODEL, "input": text},
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            logger.error("embed_error", status=resp.status_code, body=resp.text[:200])
    except Exception as e:
        logger.error("embed_exception", error=str(e))
    return None


async def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Embed multiple texts. Returns list of vectors (None where failed)."""
    if not settings.openai_api_key or not texts:
        return [None] * len(texts)
    try:
        capped = [t.strip()[:8000] for t in texts]
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                EMBED_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": EMBED_MODEL, "input": capped},
            )
            if resp.status_code == 200:
                items = sorted(resp.json()["data"], key=lambda x: x["index"])
                return [i["embedding"] for i in items]
    except Exception as e:
        logger.error("embed_batch_exception", error=str(e))
    return [None] * len(texts)
