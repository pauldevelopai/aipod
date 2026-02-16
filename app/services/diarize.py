import logging

from app.config import settings

logger = logging.getLogger(__name__)

_pipeline = None


def _get_pipeline():
    """Lazy-load the pyannote speaker diarization pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    try:
        from pyannote.audio import Pipeline

        token = settings.hf_token
        if not token:
            logger.warning("HF_TOKEN not set — pyannote diarization unavailable")
            return None

        logger.info("Loading pyannote speaker-diarization-3.1 pipeline...")
        _pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )
        logger.info("pyannote pipeline loaded")
        return _pipeline

    except ImportError:
        logger.warning("pyannote.audio not installed — diarization unavailable")
        return None
    except Exception as e:
        logger.warning(f"Failed to load pyannote pipeline: {e}")
        return None


def diarize(audio_path: str) -> list[dict] | None:
    """Run speaker diarization on an audio file using pyannote.

    Returns a list of segments: [{"speaker": "SPEAKER_00", "start": 0.5, "end": 3.2}, ...]
    Returns None if HF_TOKEN is missing or pyannote is unavailable (triggers gap-based fallback).
    """
    pipeline = _get_pipeline()
    if pipeline is None:
        return None

    try:
        logger.info(f"Running speaker diarization on {audio_path}")
        diarization = pipeline(audio_path)

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start": round(turn.start, 2),
                "end": round(turn.end, 2),
            })

        logger.info(f"Diarization complete: {len(segments)} segments, "
                     f"{len(set(s['speaker'] for s in segments))} speakers")
        return segments

    except Exception as e:
        logger.warning(f"Diarization failed: {e}")
        return None
