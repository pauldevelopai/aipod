from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pathlib import Path

from app.config import settings, BASE_DIR

db_path = BASE_DIR / "data"
db_path.mkdir(parents=True, exist_ok=True)

db_url = settings.database_url
if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
    db_url = f"sqlite:///{BASE_DIR / db_url.replace('sqlite:///', '')}"

engine = create_engine(db_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def _migrate_db():
    """Apply incremental schema migrations for existing databases."""
    import sqlite3
    from app.config import BASE_DIR

    # Resolve the actual SQLite file path
    raw_url = settings.database_url
    if raw_url.startswith("sqlite:///") and not raw_url.startswith("sqlite:////"):
        db_file = str(BASE_DIR / raw_url.replace("sqlite:///", ""))
    else:
        db_file = raw_url.replace("sqlite:///", "")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        # Get existing columns in the jobs table
        cursor.execute("PRAGMA table_info(jobs)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        # Add new Job columns if missing
        if "vocals_file" not in existing_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN vocals_file TEXT")
        if "background_file" not in existing_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN background_file TEXT")

        conn.commit()
    finally:
        conn.close()
