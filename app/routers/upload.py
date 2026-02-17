import json
import logging
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import get_db
from app.models import Job, User
from app.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRED_STAGES = {4, 6, 7}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_language: str = Form(...),
    stages: str = Form("1,2,3,4,5,6,7"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only MP3 files are accepted")

    # Parse and validate stages
    try:
        enabled_stages = sorted(set(int(s.strip()) for s in stages.split(",") if s.strip()))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid stages format")

    if not REQUIRED_STAGES.issubset(enabled_stages):
        raise HTTPException(status_code=400, detail="Stages 4, 6, and 7 are required")
    if any(s < 1 or s > 7 for s in enabled_stages):
        raise HTTPException(status_code=400, detail="Stage numbers must be 1-7")

    job_id = str(uuid.uuid4())
    upload_dir = BASE_DIR / settings.upload_dir / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Read audio duration
    audio_duration = None
    try:
        from mutagen.mp3 import MP3
        audio_info = MP3(str(file_path))
        audio_duration = int(audio_info.info.length)
    except Exception as e:
        logger.warning(f"Could not read audio duration: {e}")

    job = Job(
        id=job_id,
        user_id=user.id,
        status="pending",
        current_stage=0,
        stage_name="Queued",
        source_language="auto",
        target_language=target_language,
        original_filename=file.filename,
        original_file=str(file_path),
        enabled_stages_json=json.dumps(enabled_stages),
        audio_duration_seconds=audio_duration,
    )
    db.add(job)
    db.commit()

    # Kick off the Celery pipeline (graceful if Redis is not available)
    try:
        from app.pipeline.tasks import run_pipeline
        run_pipeline.delay(job_id)
    except Exception as e:
        logger.warning(f"Could not dispatch Celery task for job {job_id}: {e}. "
                       "Job saved — start Redis + Celery worker to process it.")
        job.stage_name = "Queued (waiting for worker)"
        db.commit()

    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
