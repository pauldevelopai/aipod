from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.config import BASE_DIR, get_language
from app.database import get_db
from app.models import User, Job, Feedback
from app.auth import require_admin

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("")
async def admin_dashboard(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.query(func.count(User.id)).scalar()
    total_jobs = db.query(func.count(Job.id)).scalar()
    completed_jobs = db.query(func.count(Job.id)).filter(Job.status == "completed").scalar()
    failed_jobs = db.query(func.count(Job.id)).filter(Job.status == "failed").scalar()
    total_feedback = db.query(func.count(Feedback.id)).scalar()

    recent_feedback = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .limit(5)
        .all()
    )
    # Preload user info for feedback
    for fb in recent_feedback:
        _ = fb.user

    recent_jobs = (
        db.query(Job)
        .order_by(Job.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "user": user,
        "total_users": total_users,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "total_feedback": total_feedback,
        "recent_feedback": recent_feedback,
        "recent_jobs": recent_jobs,
    })


@router.get("/users")
async def admin_users(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "user": user,
        "users": users,
    })


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/toggle-admin")
async def toggle_user_admin(user_id: str, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")
    target.is_admin = not target.is_admin
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/jobs")
async def admin_jobs(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    all_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(100).all()
    job_list = []
    for job in all_jobs:
        lang = get_language(job.target_language)
        lang_name = lang["name"] if lang else job.target_language
        owner = db.query(User).filter(User.id == job.user_id).first() if job.user_id else None
        job_list.append({
            **job.to_dict(),
            "target_lang_name": lang_name,
            "owner_email": owner.email if owner else "—",
        })
    return templates.TemplateResponse("admin/jobs.html", {
        "request": request,
        "user": user,
        "jobs": job_list,
    })


@router.get("/feedback")
async def admin_feedback(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    all_feedback = (
        db.query(Feedback)
        .order_by(Feedback.created_at.desc())
        .limit(100)
        .all()
    )
    for fb in all_feedback:
        _ = fb.user
    return templates.TemplateResponse("admin/feedback.html", {
        "request": request,
        "user": user,
        "feedbacks": all_feedback,
    })
