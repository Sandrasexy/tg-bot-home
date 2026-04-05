"""Voice message transcription via OpenAI Whisper API."""

import logging
import tempfile
import os

logger = logging.getLogger(__name__)


async def transcribe(file_bytes: bytes, mime: str = "audio/ogg") -> str | None:
    """Transcribe audio bytes using OpenAI Whisper. Returns text or None on failure."""
    from config import OPENAI_API_KEY

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — voice transcription unavailable")
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=OPENAI_API_KEY)

        # Write to a temp file; Whisper needs a filename with extension
        suffix = ".ogg" if "ogg" in mime else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                transcript = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="ru",
                )
            return transcript.text
        finally:
            os.unlink(tmp_path)

    except Exception as e:
        logger.error("Whisper transcription error: %s", e)
        return None
