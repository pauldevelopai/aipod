from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import BASE_DIR
from app.database import init_db
from app.routers import upload, jobs, editor, download
from app.routers import auth as auth_router
from app.routers import admin as admin_router
from app.routers import feedback as feedback_router
from app.auth import get_current_user_or_none

app = FastAPI(title="AiPod", description="Podcast Translation Pipeline")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.include_router(auth_router.router)
app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(editor.router)
app.include_router(download.router)
app.include_router(feedback_router.router)
app.include_router(admin_router.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 303:
        return RedirectResponse(url="/login", status_code=303)
    if exc.status_code in (403, 404):
        from app.database import get_db
        db = next(get_db())
        try:
            user = get_current_user_or_none(request, db)
        finally:
            db.close()
        return templates.TemplateResponse("error.html", {
            "request": request,
            "user": user,
            "status_code": exc.status_code,
            "message": exc.detail,
        }, status_code=exc.status_code)
    raise exc


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
async def index(request: Request):
    from app.config import SUPPORTED_LANGUAGES, LANGUAGE_GROUPS, get_language
    from app.database import get_db
    from app.models import Job

    db = next(get_db())
    try:
        user = get_current_user_or_none(request, db)
        if not user:
            return RedirectResponse(url="/login", status_code=303)

        job_list = (
            db.query(Job)
            .filter(Job.user_id == user.id)
            .order_by(Job.created_at.desc())
            .limit(20)
            .all()
        )
        past_jobs = []
        for job in job_list:
            lang = get_language(job.target_language)
            lang_name = lang["name"] if lang else job.target_language
            past_jobs.append({
                **job.to_dict(),
                "target_lang_name": lang_name,
            })
    finally:
        db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "languages": SUPPORTED_LANGUAGES,
        "language_groups": LANGUAGE_GROUPS,
        "past_jobs": past_jobs,
    })
