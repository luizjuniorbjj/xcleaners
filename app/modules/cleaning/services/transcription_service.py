"""
Xcleaners — Audio transcription via OpenAI Whisper.

Used by the WhatsApp pipeline to convert voice messages (audio/ogg, audio/mpeg)
into plain text so the same scheduling AI pipeline can process them.

Single public function: transcribe_audio(audio_bytes, mime_type, language=None).
Returns transcribed text or None on failure (caller decides fallback message).
"""

import logging
from io import BytesIO
from typing import Optional

from app.config import OPENAI_API_KEY

logger = logging.getLogger("xcleaners.transcription")

WHISPER_MODEL = "whisper-1"

_MIME_TO_EXT = {
    "audio/ogg": "ogg",
    "audio/ogg; codecs=opus": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "mp4",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/webm": "webm",
}


def _ext_for_mime(mime_type: Optional[str]) -> str:
    if not mime_type:
        return "ogg"
    base = mime_type.split(";")[0].strip().lower()
    return _MIME_TO_EXT.get(base, _MIME_TO_EXT.get(mime_type.lower(), "ogg"))


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: Optional[str] = "audio/ogg",
    language: Optional[str] = None,
) -> Optional[str]:
    """Transcribe audio via OpenAI Whisper.

    Args:
        audio_bytes: raw audio (e.g. OGG/Opus from WhatsApp).
        mime_type: best-effort MIME so the file extension is correct
                   (Whisper rejects unknown extensions).
        language: ISO-639-1 hint (e.g. "pt", "en", "es"). None = auto-detect.

    Returns:
        Transcribed text stripped of whitespace, or None on failure.
    """
    if not audio_bytes:
        logger.warning("[TRANSCRIBE] Empty audio bytes")
        return None
    if not OPENAI_API_KEY:
        logger.warning("[TRANSCRIBE] OPENAI_API_KEY not set — transcription disabled")
        return None

    ext = _ext_for_mime(mime_type)
    size_kb = len(audio_bytes) / 1024
    logger.info(
        "[TRANSCRIBE] audio=%.1fKB mime=%s ext=%s lang=%s",
        size_kb, mime_type, ext, language or "auto",
    )

    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.error("[TRANSCRIBE] openai package missing")
        return None

    buf = BytesIO(audio_bytes)
    buf.name = f"voice.{ext}"

    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        kwargs = {"model": WHISPER_MODEL, "file": buf}
        if language:
            kwargs["language"] = language
        result = await client.audio.transcriptions.create(**kwargs)
        text = (getattr(result, "text", "") or "").strip()
        if not text:
            logger.warning("[TRANSCRIBE] Whisper returned empty text")
            return None
        logger.info("[TRANSCRIBE] OK %d chars: %s", len(text), text[:120])
        return text
    except Exception as e:
        logger.error("[TRANSCRIBE] Whisper API error: %s", e)
        return None
