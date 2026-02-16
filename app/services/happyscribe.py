import asyncio
import json
import logging
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.happyscribe.com/api/v1"
POLL_INTERVAL = 10
MAX_POLL_ATTEMPTS = 180


def _headers():
    return {
        "Authorization": f"Bearer {settings.happyscribe_api_key}",
        "Content-Type": "application/json",
    }


async def get_upload_url() -> dict:
    """Get a signed upload URL from HappyScribe."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BASE_URL}/uploads/new",
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def upload_file(file_path: str) -> str:
    """Upload file to HappyScribe's S3 and return the signed URL."""
    upload_info = await get_upload_url()
    signed_url = upload_info["signedUrl"]

    async with httpx.AsyncClient(timeout=120) as client:
        with open(file_path, "rb") as f:
            resp = await client.put(
                signed_url,
                content=f.read(),
                headers={"Content-Type": "audio/mpeg"},
            )
            resp.raise_for_status()

    return signed_url


async def create_order(signed_url: str, language: str | None = None) -> str:
    """Create a transcription order. Language=None for auto-detect. Returns order ID."""
    async with httpx.AsyncClient(timeout=30) as client:
        order_config = {
            "service": "transcription",
            "inputs": [{"url": signed_url}],
        }
        if language:
            order_config["language"] = language
        payload = {"order": order_config}
        resp = await client.post(
            f"{BASE_URL}/orders",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def poll_order(order_id: str) -> dict:
    """Poll until transcription order completes."""
    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(MAX_POLL_ATTEMPTS):
            resp = await client.get(
                f"{BASE_URL}/orders/{order_id}",
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            state = data.get("state", "")

            if state == "finished":
                return data
            elif state in ("failed", "expired"):
                raise RuntimeError(f"HappyScribe order failed: {state}")

            logger.info(f"HappyScribe order {order_id}: {state}")
            await asyncio.sleep(POLL_INTERVAL)

    raise TimeoutError(f"HappyScribe order {order_id} timed out")


async def export_transcript(transcription_id: str) -> dict:
    """Export transcript as JSON with speaker labels and timestamps."""
    async with httpx.AsyncClient(timeout=60) as client:
        # Create export
        resp = await client.post(
            f"{BASE_URL}/exports",
            json={
                "export": {
                    "transcription_id": transcription_id,
                    "format": "json",
                    "show_speaker": True,
                    "show_timestamps": True,
                }
            },
            headers=_headers(),
        )
        resp.raise_for_status()
        export_data = resp.json()
        export_id = export_data["id"]

        # Poll for export
        for _ in range(60):
            resp = await client.get(
                f"{BASE_URL}/exports/{export_id}",
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("state") == "ready" and data.get("download_link"):
                # Download the export
                resp = await client.get(data["download_link"])
                resp.raise_for_status()
                return resp.json()

            await asyncio.sleep(5)

    raise TimeoutError("HappyScribe export timed out")


async def transcribe(file_path: str, language: str | None = None) -> tuple[str, list[dict]]:
    """Full HappyScribe pipeline: upload, order, poll, export.
    Language=None for auto-detect.
    Returns (order_id, segments) where segments is a list of dicts with
    speaker, text, start_time, end_time."""
    signed_url = await upload_file(file_path)
    order_id = await create_order(signed_url, language)
    order_data = await poll_order(order_id)

    # Get the transcription ID from the order
    transcriptions = order_data.get("transcriptions", [])
    if not transcriptions:
        raise RuntimeError("No transcriptions in HappyScribe order")

    transcription_id = transcriptions[0]["id"]
    raw_export = await export_transcript(transcription_id)

    # Normalize to our segment format
    segments = _normalize_segments(raw_export)
    return order_id, segments


def _normalize_segments(raw_export: dict) -> list[dict]:
    """Convert HappyScribe export to normalized segment format."""
    segments = []
    results = raw_export.get("results", raw_export.get("segments", []))

    for item in results:
        segment = {
            "speaker": item.get("speaker", "Speaker"),
            "text": item.get("text", item.get("content", "")),
            "start_time": item.get("start_time", item.get("start", 0)),
            "end_time": item.get("end_time", item.get("end", 0)),
        }
        if segment["text"].strip():
            segments.append(segment)

    return segments
