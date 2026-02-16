import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy.orm import Session

from app.config import BASE_DIR, SUPPORTED_LANGUAGES, get_language
from app.database import get_db
from app.models import Job


def _md_to_html(text: str) -> str:
    """Simple markdown to HTML for report rendering."""
    html = re.sub(r"^### (.+)$", r"<h3 class='text-white font-semibold mt-4 mb-2'>\1</h3>", text, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h3 class='text-white font-semibold mt-4 mb-2'>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong class='text-white'>\1</strong>", html)
    html = re.sub(r"^- (.+)$", r"<li class='ml-4'>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li.*?</li>\n?)+", r"<ul class='list-disc mb-3'>\g<0></ul>", html)
    html = html.replace("\n\n", "</p><p class='mb-3'>")
    html = f"<p class='mb-3'>{html}</p>"
    return html


def _format_datetime(dt) -> str:
    """Format a datetime for display."""
    if not dt:
        return "Unknown"
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%d %b %Y, %H:%M")


def _build_download_filename(job) -> str:
    """Build a descriptive filename: originalname_language_timestamp.mp3"""
    # Get base name from original filename
    if job.original_filename:
        base = Path(job.original_filename).stem
    else:
        base = f"aipod_{job.id[:8]}"

    # Get target language name
    lang = get_language(job.target_language)
    lang_name = lang["name"] if lang else job.target_language

    # Timestamp from completion
    ts = job.updated_at or job.created_at
    if ts:
        ts_str = ts.strftime("%Y%m%d_%H%M")
    else:
        ts_str = "unknown"

    # Clean filename
    safe_base = re.sub(r'[^\w\s-]', '', base).strip()
    safe_lang = re.sub(r'[^\w\s-]', '', lang_name).strip()

    return f"{safe_base}_{safe_lang}_{ts_str}.mp3"


router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/jobs/{job_id}/download")
async def download_page(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed yet")

    # Parse report
    report_html = ""
    if job.report_json:
        report_data = json.loads(job.report_json)
        report_html = _md_to_html(report_data.get("report", ""))

    # Get target language name
    lang = get_language(job.target_language)
    target_lang_name = lang["name"] if lang else job.target_language

    return templates.TemplateResponse("download.html", {
        "request": request,
        "job": job.to_dict(),
        "languages": SUPPORTED_LANGUAGES,
        "report": Markup(report_html),
        "target_lang_name": target_lang_name,
        "created_at": _format_datetime(job.created_at),
        "completed_at": _format_datetime(job.updated_at),
    })


@router.get("/jobs/{job_id}/download/original")
async def download_original(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.original_file:
        raise HTTPException(status_code=404, detail="Original file not available")

    file_path = Path(job.original_file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Original file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=job.original_filename or f"original_{job_id[:8]}.mp3",
    )


@router.get("/jobs/{job_id}/download/file")
async def download_file(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed" or not job.output_file:
        raise HTTPException(status_code=400, detail="Output file not available")

    file_path = Path(job.output_file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=_build_download_filename(job),
    )
