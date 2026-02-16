from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import BASE_DIR
from app.database import init_db
from app.routers import upload, jobs, editor, download

app = FastAPI(title="AiPod", description="Podcast Translation Pipeline")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app.include_router(upload.router)
app.include_router(jobs.router)
app.include_router(editor.router)
app.include_router(download.router)


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
        jobs = db.query(Job).order_by(Job.created_at.desc()).limit(20).all()
        past_jobs = []
        for job in jobs:
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
        "languages": SUPPORTED_LANGUAGES,
        "language_groups": LANGUAGE_GROUPS,
        "past_jobs": past_jobs,
    })
