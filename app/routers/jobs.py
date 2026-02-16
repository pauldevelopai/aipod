import asyncio
import json
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import BASE_DIR, SUPPORTED_LANGUAGES
from app.database import get_db
from app.models import Job

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

STAGE_NAMES = {
    0: "Queued",
    1: "Audio Cleanup (Auphonic)",
    2: "Source Separation (Demucs)",
    3: "Transcription + Diarization (Whisper + pyannote)",
    4: "Translation (Google + Claude)",
    5: "Voice Cloning (ElevenLabs)",
    6: "Speech Generation + Mix (ElevenLabs TTS)",
}
TOTAL_STAGES = 6


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    detected_langs = json.loads(job.detected_languages_json) if job.detected_languages_json else []

    return templates.TemplateResponse("status.html", {
        "request": request,
        "job": job.to_dict(),
        "stage_names": STAGE_NAMES,
        "languages": SUPPORTED_LANGUAGES,
        "detected_languages": detected_langs,
    })


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Resume from the stage that failed
    resume_stage = job.current_stage or 1
    job.status = "pending"
    job.stage_name = "Resuming..."
    job.error_message = None
    db.commit()

    try:
        from app.pipeline.tasks import run_pipeline
        run_pipeline.delay(job_id, start_from=resume_stage)
    except Exception as e:
        logger.warning(f"Could not dispatch retry for job {job_id}: {e}")
        job.stage_name = "Queued (waiting for worker)"
        db.commit()

    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str, db: Session = Depends(get_db)):
    async def event_generator():
        while True:
            db_session = next(get_db())
            try:
                job = db_session.query(Job).filter(Job.id == job_id).first()
                if not job:
                    yield {"event": "error", "data": json.dumps({"error": "Job not found"})}
                    return

                data = {
                    "status": job.status,
                    "current_stage": job.current_stage,
                    "stage_name": job.stage_name or STAGE_NAMES.get(job.current_stage, ""),
                    "error_message": job.error_message,
                    "detected_languages": json.loads(job.detected_languages_json) if job.detected_languages_json else None,
                }
                yield {"event": "status", "data": json.dumps(data)}

                if job.status in ("completed", "failed", "awaiting_review"):
                    return
            finally:
                db_session.close()

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())
