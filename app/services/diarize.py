import gc
import logging
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _load_pipeline():
    """Load the pyannote speaker diarization pipeline (not cached — freed after use)."""
    try:
        from pyannote.audio import Pipeline

        token = settings.hf_token
        if not token:
            logger.warning("HF_TOKEN not set — pyannote diarization unavailable")
            return None

        logger.info("Loading pyannote speaker-diarization-3.1 pipeline...")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )
        logger.info("pyannote pipeline loaded")
        return pipeline

    except ImportError:
        logger.warning("pyannote.audio not installed — diarization unavailable")
        return None
    except Exception as e:
        logger.warning(f"Failed to load pyannote pipeline: {e}")
        return None


def _convert_to_wav(audio_path: str) -> str | None:
    """Convert MP3 to WAV for pyannote compatibility (avoids sample count mismatch)."""
    if not audio_path.lower().endswith(".mp3"):
        return None
    try:
        from pydub import AudioSegment
        wav_path = str(Path(audio_path).with_suffix(".diarize.wav"))
        audio = AudioSegment.from_mp3(audio_path)
        audio.export(wav_path, format="wav")
        logger.info(f"Converted {Path(audio_path).name} to WAV for diarization")
        return wav_path
    except Exception as e:
        logger.warning(f"MP3→WAV conversion failed: {e}")
        return None


def diarize(audio_path: str) -> list[dict] | None:
    """Run speaker diarization on an audio file using pyannote.

    Returns a list of segments: [{"speaker": "SPEAKER_00", "start": 0.5, "end": 3.2}, ...]
    Returns None if HF_TOKEN is missing or pyannote is unavailable (triggers gap-based fallback).
    """
    pipeline = _load_pipeline()
    if pipeline is None:
        return None

    try:
        # pyannote 4.x is strict about sample counts — convert MP3 to WAV
        wav_path = _convert_to_wav(audio_path)
        diarize_path = wav_path or audio_path

        logger.info(f"Running speaker diarization on {diarize_path}")
        diarization = pipeline(diarize_path)

        segments = []
        # pyannote 4.x returns an Annotation with itertracks()
        if hasattr(diarization, 'itertracks'):
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    "speaker": speaker,
                    "start": round(turn.start, 2),
                    "end": round(turn.end, 2),
                })
        else:
            # Fallback: iterate directly (some pyannote versions)
            for item in diarization:
                segments.append({
                    "speaker": item.get("speaker", "SPEAKER_00"),
                    "start": round(item.get("start", 0), 2),
                    "end": round(item.get("end", 0), 2),
                })

        logger.info(f"Diarization complete: {len(segments)} segments, "
                     f"{len(set(s['speaker'] for s in segments))} speakers")

        # Clean up temp WAV
        if wav_path:
            try:
                Path(wav_path).unlink()
            except OSError:
                pass

        return segments

    except Exception as e:
        logger.warning(f"Diarization failed: {e}")
        return None
    finally:
        # Free the pipeline to release RAM for Whisper
        del pipeline
        gc.collect()
