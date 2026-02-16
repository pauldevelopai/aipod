import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io/v1"


def _headers():
    return {
        "xi-api-key": settings.elevenlabs_api_key,
    }


async def clone_voice(name: str, audio_path: str) -> str:
    """Clone a voice from an audio sample. Returns voice_id."""
    async with httpx.AsyncClient(timeout=120) as client:
        with open(audio_path, "rb") as f:
            resp = await client.post(
                f"{BASE_URL}/voices/add",
                headers=_headers(),
                data={"name": name, "description": f"Cloned voice for {name}"},
                files={"files": (Path(audio_path).name, f, "audio/mpeg")},
            )
            resp.raise_for_status()
            return resp.json()["voice_id"]


async def text_to_speech(
    text: str,
    voice_id: str,
    output_path: str,
    model_id: str = "eleven_multilingual_v2",
) -> str:
    """Generate speech from text using a cloned voice. Returns output file path."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{BASE_URL}/text-to-speech/{voice_id}",
            headers={**_headers(), "Content-Type": "application/json"},
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.5,
                    "use_speaker_boost": True,
                },
            },
        )
        resp.raise_for_status()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)

    return output_path


async def delete_voice(voice_id: str) -> None:
    """Delete a cloned voice to free up quota."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(
            f"{BASE_URL}/voices/{voice_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
