import asyncio
import json
import logging

from fastapi import APIRouter, Form, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import BASE_DIR, SUPPORTED_LANGUAGES, LANGUAGE_GROUPS, get_language
from app.database import get_db
from app.models import Job, User
from app.auth import require_user, get_user_job

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

STAGE_NAMES = {
    0: "Queued",
    1: "Audio Cleanup (Auphonic)",
    2: "Source Separation",
    3: "Speaker Diarization (pyannote)",
    4: "Transcription (Whisper)",
    5: "Translation (Google + Claude)",
    6: "Voice Cloning (ElevenLabs)",
    7: "Speech Generation + Mix (ElevenLabs TTS)",
}
TOTAL_STAGES = 7


@router.get("/jobs/{job_id}")
async def job_status(job_id: str, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    job = get_user_job(job_id, user, db)

    detected_langs = json.loads(job.detected_languages_json) if job.detected_languages_json else []
    enabled_stages = json.loads(job.enabled_stages_json) if job.enabled_stages_json else [1,2,3,4,5,6,7]

    return templates.TemplateResponse("status.html", {
        "request": request,
        "user": user,
        "job": job.to_dict(),
        "stage_names": STAGE_NAMES,
        "languages": SUPPORTED_LANGUAGES,
        "language_groups": LANGUAGE_GROUPS,
        "detected_languages": detected_langs,
        "enabled_stages": enabled_stages,
    })


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
    job = get_user_job(job_id, user, db)

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
async def job_events(job_id: str, user: User = Depends(require_user), db: Session = Depends(get_db)):
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
                    "enabled_stages": json.loads(job.enabled_stages_json) if job.enabled_stages_json else [1,2,3,4,5,6,7],
                    "stage_log": json.loads(job.stage_log) if job.stage_log else [],
                    "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                }
                yield {"event": "status", "data": json.dumps(data)}

                if job.status in ("completed", "failed", "awaiting_review"):
                    return
            finally:
                db_session.close()

            await asyncio.sleep(2)

    return EventSourceResponse(event_generator())


@router.post("/jobs/{job_id}/retranslate")
async def retranslate_job(
    job_id: str,
    target_language: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Create a new job that reuses existing audio/transcript/voices but translates to a new language."""
    original_job = get_user_job(job_id, user, db)
    if original_job.status != "completed":
        raise HTTPException(status_code=400, detail="Can only re-translate completed jobs")

    # Validate target language
    lang = get_language(target_language)
    if not lang:
        raise HTTPException(status_code=400, detail="Unsupported language")

    # Inherit parent's enabled stages but always enable 4, 5, 6
    parent_stages = json.loads(original_job.enabled_stages_json) if original_job.enabled_stages_json else [1,2,3,4,5,6,7]
    retranslate_stages = sorted(set(parent_stages) | {5, 6, 7})

    # Create new job reusing stages 1-3 outputs and voice clones
    new_job = Job(
        user_id=user.id,
        status="pending",
        current_stage=0,
        stage_name="Queued",
        source_language=original_job.source_language,
        target_language=target_language,
        detected_languages_json=original_job.detected_languages_json,
        original_filename=original_job.original_filename,
        original_file=original_job.original_file,
        cleaned_file=original_job.cleaned_file,
        vocals_file=original_job.vocals_file,
        background_file=original_job.background_file,
        transcript_json=original_job.transcript_json,
        voice_map_json=original_job.voice_map_json,
        enabled_stages_json=json.dumps(retranslate_stages),
        audio_duration_seconds=original_job.audio_duration_seconds,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Start pipeline from stage 4 (translation) — stages 1-3 skipped (data exists),
    # stage 5 skipped (voice_map_json exists)
    try:
        from app.pipeline.tasks import run_pipeline
        run_pipeline.delay(new_job.id, start_from=5)
    except Exception as e:
        logger.warning(f"Could not dispatch retranslate job {new_job.id}: {e}")
        new_job.stage_name = "Queued (waiting for worker)"
        db.commit()

    return RedirectResponse(url=f"/jobs/{new_job.id}", status_code=303)
