import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)

    jobs = relationship("Job", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)  # 1-5 optional
    job_id = Column(String, ForeignKey("jobs.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="feedbacks")
    job = relationship("Job")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, default="pending")  # pending, processing, awaiting_review, completed, failed
    current_stage = Column(Integer, default=0)  # 1-6
    stage_name = Column(String, default="")

    user = relationship("User", back_populates="jobs")

    source_language = Column(String, nullable=False, default="auto")  # "auto" = detect automatically
    target_language = Column(String, nullable=False)
    detected_languages_json = Column(Text, nullable=True)  # JSON summary of detected languages

    # File paths
    original_filename = Column(String, nullable=True)  # Original upload filename
    original_file = Column(Text, nullable=True)
    cleaned_file = Column(Text, nullable=True)
    vocals_file = Column(Text, nullable=True)  # Separated vocals track
    background_file = Column(Text, nullable=True)  # Separated background (music/SFX) track
    transcript_json = Column(Text, nullable=True)
    translated_json = Column(Text, nullable=True)
    edited_json = Column(Text, nullable=True)
    voice_map_json = Column(Text, nullable=True)
    output_file = Column(Text, nullable=True)
    report_json = Column(Text, nullable=True)  # JSON pipeline report

    # External IDs
    auphonic_production_id = Column(String, nullable=True)
    happyscribe_order_id = Column(String, nullable=True)

    # Metadata
    error_message = Column(Text, nullable=True)
    stage_log = Column(Text, nullable=True)  # JSON array of {"ts": "...", "msg": "..."} log entries
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "current_stage": self.current_stage,
            "stage_name": self.stage_name,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "detected_languages_json": self.detected_languages_json,
            "original_filename": self.original_filename,
            "original_file": self.original_file,
            "cleaned_file": self.cleaned_file,
            "vocals_file": self.vocals_file,
            "background_file": self.background_file,
            "transcript_json": self.transcript_json,
            "translated_json": self.translated_json,
            "edited_json": self.edited_json,
            "voice_map_json": self.voice_map_json,
            "output_file": self.output_file,
            "report_json": self.report_json,
            "error_message": self.error_message,
            "stage_log": self.stage_log,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SpeakerProfile(Base):
    __tablename__ = "speaker_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)  # "Speaker 1" or user-assigned
    embedding_json = Column(Text)  # JSON: 256-dim resemblyzer vector
    elevenlabs_voice_id = Column(String)  # Cached ElevenLabs voice ID
    sample_file = Column(Text)  # Path to audio sample used for cloning
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
