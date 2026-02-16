from fastapi import Request, HTTPException, Depends
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, Job

_signer = URLSafeTimedSerializer(settings.secret_key)


def create_session_cookie(user_id: str) -> str:
    return _signer.dumps(user_id)


def read_session_cookie(cookie: str) -> str | None:
    try:
        return _signer.loads(cookie, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user_or_none(
    request: Request, db: Session = Depends(get_db)
) -> User | None:
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        return None
    user_id = read_session_cookie(cookie)
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    return user


def require_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    user = get_current_user_or_none(request, db)
    if not user:
        raise HTTPException(status_code=303, detail="Login required")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def get_user_job(
    job_id: str, user: User, db: Session
) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not user.is_admin and job.user_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return job
