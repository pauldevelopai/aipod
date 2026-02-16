from celery import Celery
from celery.signals import worker_ready, worker_shutting_down

from app.config import settings

celery_app = Celery(
    "aipod",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    include=["app.pipeline.tasks"],
    # Re-deliver unacked tasks after 30 min (covers long separation stage)
    broker_transport_options={"visibility_timeout": 1800},
    # Hard kill tasks after 20 min to prevent infinite hangs
    task_time_limit=1200,
    # Soft limit at 18 min — gives task a chance to clean up
    task_soft_time_limit=1080,
)


@worker_ready.connect
def recover_orphaned_jobs(sender=None, **kwargs):
    """On worker startup, reset any 'processing' jobs to 'failed'.
    These are leftovers from a previous crash/restart."""
    from app.database import SessionLocal
    from app.models import Job

    db = SessionLocal()
    try:
        orphaned = db.query(Job).filter(Job.status == "processing").all()
        for job in orphaned:
            job.status = "failed"
            job.error_message = "Worker restarted during processing — please retry"
        if orphaned:
            db.commit()
            print(f"[recovery] Reset {len(orphaned)} orphaned jobs to failed")
    finally:
        db.close()


@worker_shutting_down.connect
def mark_inflight_failed(sender=None, **kwargs):
    """On graceful shutdown, mark any 'processing' jobs as failed."""
    from app.database import SessionLocal
    from app.models import Job

    db = SessionLocal()
    try:
        inflight = db.query(Job).filter(Job.status == "processing").all()
        for job in inflight:
            job.status = "failed"
            job.error_message = "Worker shutting down — please retry"
        if inflight:
            db.commit()
            print(f"[shutdown] Marked {len(inflight)} in-flight jobs as failed")
    finally:
        db.close()
