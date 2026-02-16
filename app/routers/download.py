import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy.orm import Session

from app.config import BASE_DIR, SUPPORTED_LANGUAGES, LANGUAGE_GROUPS, get_language
from app.database import get_db
from app.models import Job


def _md_to_html(text: str) -> str:
    """Convert markdown report to HTML. Handles headers, bold, and nested bullets."""
    lines = text.split("\n")
    html_parts = []
    in_list = False
    in_sublist = False

    for line in lines:
        stripped = line.strip()

        # Empty line — close any open lists
        if not stripped:
            if in_sublist:
                html_parts.append("</ul>")
                in_sublist = False
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # Bold: **text**
        stripped = re.sub(r"\*\*(.+?)\*\*", r"<strong class='text-white'>\1</strong>", stripped)

        # Headers
        if stripped.startswith("### "):
            if in_sublist:
                html_parts.append("</ul>")
                in_sublist = False
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3 class='text-white font-semibold mt-5 mb-2'>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            if in_sublist:
                html_parts.append("</ul>")
                in_sublist = False
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3 class='text-white font-semibold mt-5 mb-2'>{stripped[3:]}</h3>")

        # Sub-bullet (indented)
        elif line.startswith("  - "):
            if not in_sublist:
                in_sublist = True
                html_parts.append("<ul class='list-disc ml-8 mb-1'>")
            content = stripped[2:]  # remove "- "
            html_parts.append(f"<li class='text-gray-400 text-sm'>{content}</li>")

        # Top-level bullet
        elif stripped.startswith("- "):
            if in_sublist:
                html_parts.append("</ul>")
                in_sublist = False
            if not in_list:
                in_list = True
                html_parts.append("<ul class='list-disc ml-4 mb-2'>")
            content = stripped[2:]
            html_parts.append(f"<li class='mb-1'>{content}</li>")

        # Plain text
        else:
            if in_sublist:
                html_parts.append("</ul>")
                in_sublist = False
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p class='mb-2 text-gray-300'>{stripped}</p>")

    # Close any open lists
    if in_sublist:
        html_parts.append("</ul>")
    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


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
        "language_groups": LANGUAGE_GROUPS,
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
