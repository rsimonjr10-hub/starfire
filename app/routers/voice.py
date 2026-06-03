"""
Voice note ingestion endpoint.

POST /voice/transcribe
  - Accepts an audio file (multipart) + dashboard HMAC token for auth
  - Transcribes via Whisper (Groq or OpenAI)
  - Passes transcript through the STARFIRE brain
  - Returns {transcript, response}

This lets mobile apps or the dashboard POST audio directly rather than
going through Telegram.
"""
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.integrations.whisper import transcribe
from app.models.user import User
from app.starfire.decision import DecisionEngine

router = APIRouter(prefix="/voice", tags=["voice"])


# ── Auth (same HMAC token as dashboard) ───────────────────────────────────

def _make_token(telegram_id: int) -> str:
    return hmac.new(
        settings.app_secret_key.encode(),
        str(telegram_id).encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        for u in users:
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/transcribe")
async def voice_transcribe(
    audio: UploadFile = File(...),
    user: User = Depends(_get_user),
):
    """
    Transcribe an audio file and route the text through the STARFIRE brain.

    Form fields:
      audio  — audio file (ogg, mp3, wav, webm, m4a, flac)
      token  — dashboard HMAC token (query param)

    Returns:
      {transcript: str, response: str}
    """
    if not settings.groq_api_key and not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="No Whisper provider configured. Set GROQ_API_KEY or OPENAI_API_KEY.",
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    filename = audio.filename or "voice.ogg"
    transcript = await transcribe(audio_bytes, filename)

    if not transcript:
        raise HTTPException(status_code=422, detail="Transcription failed — check audio quality and provider key")

    # Run through brain
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one()
        engine = DecisionEngine(session)
        try:
            response = await engine.process_message(db_user, transcript)
            await session.commit()
        except Exception:
            await session.rollback()
            raise HTTPException(status_code=500, detail="Brain processing failed")

    return {"transcript": transcript, "response": response}


@router.post("/transcribe/raw")
async def voice_transcribe_only(
    audio: UploadFile = File(...),
    user: User = Depends(_get_user),
):
    """Transcribe only — returns the text without running it through the brain."""
    if not settings.groq_api_key and not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="No Whisper provider configured")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    filename = audio.filename or "voice.ogg"
    transcript = await transcribe(audio_bytes, filename)

    if not transcript:
        raise HTTPException(status_code=422, detail="Transcription failed")

    return {"transcript": transcript}
