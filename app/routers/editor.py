import json
import logging

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR, SUPPORTED_LANGUAGES
from app.database import get_db
from app.models import Job

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/jobs/{job_id}/edit")
async def edit_translation(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "awaiting_review":
        raise HTTPException(status_code=400, detail="Job is not ready for review")

    transcript = json.loads(job.transcript_json) if job.transcript_json else []
    translated = json.loads(job.translated_json) if job.translated_json else []

    return templates.TemplateResponse("editor.html", {
        "request": request,
        "job": job.to_dict(),
        "transcript": transcript,
        "translated": translated,
        "languages": SUPPORTED_LANGUAGES,
    })


@router.post("/jobs/{job_id}/edit")
async def save_translation(
    job_id: str,
    edited_segments: str = Form(...),
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "awaiting_review":
        raise HTTPException(status_code=400, detail="Job is not ready for review")

    job.edited_json = edited_segments
    job.status = "processing"
    job.current_stage = 6
    job.stage_name = "Speech Generation + Mix (ElevenLabs TTS)"
    db.commit()

    # Resume the pipeline from stage 6 (graceful if Redis is not available)
    try:
        from app.pipeline.tasks import resume_pipeline
        resume_pipeline.delay(job_id)
    except Exception as e:
        logger.warning(f"Could not dispatch Celery resume for job {job_id}: {e}")
        job.stage_name = "Speech Generation + Mix (waiting for worker)"
        db.commit()

    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
