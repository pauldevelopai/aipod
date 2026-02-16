import json
import logging
import uuid
from datetime import datetime, timezone

import numpy as np

from app.database import SessionLocal
from app.models import SpeakerProfile

logger = logging.getLogger(__name__)

_encoder = None


def _get_encoder():
    """Lazy-load the resemblyzer voice encoder."""
    global _encoder
    if _encoder is not None:
        return _encoder

    try:
        from resemblyzer import VoiceEncoder
        logger.info("Loading resemblyzer voice encoder...")
        _encoder = VoiceEncoder()
        logger.info("Resemblyzer encoder loaded")
        return _encoder
    except ImportError:
        logger.warning("resemblyzer not installed — fingerprint matching unavailable")
        return None
    except Exception as e:
        logger.warning(f"Failed to load resemblyzer encoder: {e}")
        return None


def compute_embedding(audio_path: str) -> list[float] | None:
    """Compute a 256-dim speaker embedding vector from an audio file.

    Returns a list of floats, or None if resemblyzer is unavailable.
    """
    encoder = _get_encoder()
    if encoder is None:
        return None

    try:
        from resemblyzer import preprocess_wav
        wav = preprocess_wav(audio_path)
        embedding = encoder.embed_utterance(wav)
        return embedding.tolist()
    except Exception as e:
        logger.warning(f"Failed to compute embedding for {audio_path}: {e}")
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    dot = np.dot(a_arr, b_arr)
    norm = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def find_matching_profile(
    embedding: list[float], threshold: float = 0.85
) -> SpeakerProfile | None:
    """Search all stored speaker profiles for a cosine similarity match.

    Returns the best matching SpeakerProfile if similarity >= threshold, else None.
    """
    db = SessionLocal()
    try:
        profiles = db.query(SpeakerProfile).all()
        best_match = None
        best_score = 0.0

        for profile in profiles:
            stored_embedding = json.loads(profile.embedding_json)
            score = _cosine_similarity(embedding, stored_embedding)
            if score >= threshold and score > best_score:
                best_score = score
                best_match = profile

        if best_match:
            logger.info(f"Found matching speaker profile '{best_match.name}' "
                        f"(similarity={best_score:.3f})")
            # Update last_used_at
            best_match.last_used_at = datetime.now(timezone.utc)
            db.commit()
            # Expunge so the object survives session close
            db.expunge(best_match)
            return best_match

        return None
    finally:
        db.close()


def create_profile(
    name: str,
    embedding: list[float],
    voice_id: str,
    sample_file: str,
) -> SpeakerProfile:
    """Store a new speaker profile in the database."""
    db = SessionLocal()
    try:
        profile = SpeakerProfile(
            id=str(uuid.uuid4()),
            name=name,
            embedding_json=json.dumps(embedding),
            elevenlabs_voice_id=voice_id,
            sample_file=sample_file,
            created_at=datetime.now(timezone.utc),
            last_used_at=datetime.now(timezone.utc),
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info(f"Created speaker profile '{name}' with voice_id={voice_id}")
        db.expunge(profile)
        return profile
    finally:
        db.close()
