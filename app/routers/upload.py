import logging
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings, BASE_DIR
from app.database import get_db
from app.models import Job

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    target_language: str = Form(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only MP3 files are accepted")

    job_id = str(uuid.uuid4())
    upload_dir = BASE_DIR / settings.upload_dir / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / file.filename
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = Job(
        id=job_id,
        status="pending",
        current_stage=0,
        stage_name="Queued",
        source_language="auto",
        target_language=target_language,
        original_filename=file.filename,
        original_file=str(file_path),
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
