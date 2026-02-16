import asyncio
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://auphonic.com/api"
POLL_INTERVAL = 10
MAX_POLL_ATTEMPTS = 180  # 30 minutes max


def _headers():
    return {"Authorization": f"Bearer {settings.auphonic_api_key}"}


async def create_production(file_path: str, preset: str | None = None) -> str:
    """Upload audio to Auphonic and create a production. Returns production UUID."""
    async with httpx.AsyncClient(timeout=120) as client:
        payload = {
            "output_files": [{"format": "mp3", "bitrate": "192"}],
            "algorithms": {
                "leveler": True,
                "denoise": True,
                "loudness_target": -16,
            },
        }
        if preset:
            payload["preset"] = preset

        resp = await client.post(
            f"{BASE_URL}/productions.json",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()
        production_uuid = resp.json()["data"]["uuid"]

        # Upload audio file
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{BASE_URL}/production/{production_uuid}/upload.json",
                files={"input_file": (Path(file_path).name, f, "audio/mpeg")},
                headers=_headers(),
            )
            resp.raise_for_status()

        return production_uuid


async def start_production(production_uuid: str) -> None:
    """Start processing a production."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/production/{production_uuid}/start.json",
            headers=_headers(),
        )
        resp.raise_for_status()


async def poll_production(production_uuid: str) -> dict:
    """Poll until production completes. Returns production data."""
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(MAX_POLL_ATTEMPTS):
            resp = await client.get(
                f"{BASE_URL}/production/{production_uuid}.json",
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data.get("status_string", "")

            if status == "Done":
                return data
            elif status in ("Error", "Incomplete"):
                raise RuntimeError(f"Auphonic production failed: {data.get('error_message', status)}")

            logger.info(f"Auphonic production {production_uuid}: {status}")
            await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"Auphonic production {production_uuid} timed out")


async def download_output(production_data: dict, output_path: str) -> str:
    """Download the processed output file."""
    output_files = production_data.get("output_files", [])
    if not output_files:
        raise RuntimeError("No output files from Auphonic")

    download_url = output_files[0].get("download_url")
    if not download_url:
        raise RuntimeError("No download URL in Auphonic output")

    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(download_url, headers=_headers())
        resp.raise_for_status()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)

    return output_path


async def process_audio(file_path: str, output_path: str) -> str:
    """Full Auphonic pipeline: create, start, poll, download."""
    uuid = await create_production(file_path)
    await start_production(uuid)
    data = await poll_production(uuid)
    await download_output(data, output_path)
    return uuid
