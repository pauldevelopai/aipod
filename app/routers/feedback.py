from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.database import get_db
from app.models import User, Feedback
from app.auth import require_user

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/feedback")
async def feedback_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    past = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id)
        .order_by(Feedback.created_at.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "user": user,
        "past_feedback": past,
        "success": False,
    })


@router.post("/feedback")
async def submit_feedback(
    request: Request,
    message: str = Form(...),
    rating: int = Form(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if rating is not None and (rating < 1 or rating > 5):
        rating = None

    fb = Feedback(
        user_id=user.id,
        message=message.strip(),
        rating=rating,
    )
    db.add(fb)
    db.commit()

    past = (
        db.query(Feedback)
        .filter(Feedback.user_id == user.id)
        .order_by(Feedback.created_at.desc())
        .limit(20)
        .all()
    )
    return templates.TemplateResponse("feedback.html", {
        "request": request,
        "user": user,
        "past_feedback": past,
        "success": True,
    })
