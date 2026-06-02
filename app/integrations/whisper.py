"""
Audio transcription via Whisper / GPT-4o Speech.

Priority: Groq (fast, free tier) → OpenAI gpt-4o-transcribe → gpt-4o-mini-transcribe → error.
Both APIs share the same multipart interface so the same helper works for both.
"""
import io
from typing import Optional

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"


async def _call_whisper(
    api_url: str,
    api_key: str,
    audio_bytes: bytes,
    filename: str,
    model: str,
) -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": (filename, io.BytesIO(audio_bytes), _mime(filename))}
    data = {"model": model, "response_format": "json"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(api_url, headers=headers, files=files, data=data)
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            logger.error("whisper_error", url=api_url, status=resp.status_code, body=resp.text[:200])
    except Exception as e:
        logger.error("whisper_exception", url=api_url, error=str(e))
    return None


def _mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return {
        "ogg": "audio/ogg",
        "mp3": "audio/mpeg",
        "mp4": "audio/mp4",
        "wav": "audio/wav",
        "webm": "audio/webm",
        "m4a": "audio/mp4",
        "flac": "audio/flac",
    }.get(ext, "audio/ogg")


async def transcribe(audio_bytes: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """
    Transcribe audio bytes to text.
    Priority: Groq whisper-large-v3-turbo (fast) → OpenAI gpt-4o-transcribe → gpt-4o-mini-transcribe.
    Returns None if all providers unavailable or fail.
    """
    if settings.groq_api_key:
        text = await _call_whisper(
            _GROQ_URL, settings.groq_api_key, audio_bytes, filename, "whisper-large-v3-turbo"
        )
        if text is not None:
            return text
        logger.warning("whisper_groq_failed_trying_openai")

    if settings.openai_api_key:
        text = await _call_whisper(
            _OPENAI_URL, settings.openai_api_key, audio_bytes, filename, "gpt-4o-transcribe"
        )
        if text is not None:
            return text
        logger.warning("whisper_gpt4o_transcribe_failed_trying_mini")
        return await _call_whisper(
            _OPENAI_URL, settings.openai_api_key, audio_bytes, filename, "gpt-4o-mini-transcribe"
        )

    logger.error("whisper_no_provider", hint="Set GROQ_API_KEY or OPENAI_API_KEY")
    return None
