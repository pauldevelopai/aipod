from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from app.config import BASE_DIR, settings
from app.database import get_db
from app.models import User
from app.auth import create_session_cookie

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "user": None, "error": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not bcrypt.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "user": None,
            "error": "Invalid email or password",
        })
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "user": None,
            "error": "Account is disabled",
        })

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_cookie(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "user": None, "error": None})


@router.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()

    if password != password_confirm:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "user": None,
            "error": "Passwords do not match",
        })

    if len(password) < 6:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "user": None,
            "error": "Password must be at least 6 characters",
        })

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "user": None,
            "error": "An account with this email already exists",
        })

    user = User(
        email=email,
        password_hash=bcrypt.hash(password),
        display_name=display_name.strip() or None,
        is_admin=False,
        is_active=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_cookie(user.id),
        max_age=settings.session_max_age,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key=settings.session_cookie_name)
    return response
