import logging

from faster_whisper import WhisperModel

from app.config import settings

logger = logging.getLogger(__name__)

_model = None

# Model RAM requirements (approximate, int8):
# tiny: ~75MB  | base: ~150MB | small: ~500MB | medium: ~1.5GB | large-v3: ~3GB
_MODEL_SIZES = {
    "tiny": "~75MB RAM",
    "base": "~150MB RAM",
    "small": "~500MB RAM",
    "medium": "~1.5GB RAM",
    "large-v3": "~3GB RAM",
}


def _get_model() -> WhisperModel:
    """Lazy-load the Whisper model (downloaded on first use)."""
    global _model
    if _model is None:
        model_name = settings.whisper_model
        size_info = _MODEL_SIZES.get(model_name, "unknown size")
        logger.info(f"Loading Whisper model ({model_name}, {size_info}) — first run downloads the model")
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
        logger.info(f"Whisper model ({model_name}) loaded")
    return _model


def transcribe(file_path: str, diarization_segments: list[dict] | None = None) -> list[dict]:
    """Transcribe an audio file using Whisper locally.
    Returns a list of segments with speaker, text, start_time, end_time.

    If diarization_segments is provided (from pyannote), each Whisper segment
    is assigned the pyannote speaker with maximum time overlap.
    Otherwise falls back to gap-based speaker detection."""
    model = _get_model()

    segments_iter, info = model.transcribe(
        file_path,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    logger.info(f"Detected language: {info.language} (probability {info.language_probability:.2f})")

    raw_segments = list(segments_iter)

    if diarization_segments:
        result = _assign_speakers_from_diarization(raw_segments, diarization_segments)
    else:
        result = _assign_speakers_gap_based(raw_segments)

    logger.info(f"Transcription complete: {len(result)} segments")
    return result


def _assign_speakers_from_diarization(
    whisper_segments: list, diarization_segments: list[dict]
) -> list[dict]:
    """Assign speaker labels by finding the pyannote segment with maximum time overlap."""
    # Build a mapping of unique pyannote speaker IDs to friendly names
    unique_speakers = sorted(set(s["speaker"] for s in diarization_segments))
    speaker_names = {spk: f"Speaker {i + 1}" for i, spk in enumerate(unique_speakers)}

    result = []
    for seg in whisper_segments:
        text = seg.text.strip()
        if not text:
            continue

        seg_start = seg.start
        seg_end = seg.end

        # Find the diarization segment with maximum overlap
        best_speaker = None
        best_overlap = 0.0

        for diar_seg in diarization_segments:
            overlap_start = max(seg_start, diar_seg["start"])
            overlap_end = min(seg_end, diar_seg["end"])
            overlap = max(0.0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = diar_seg["speaker"]

        speaker_label = speaker_names.get(best_speaker, "Speaker 1") if best_speaker else "Speaker 1"

        result.append({
            "speaker": speaker_label,
            "text": text,
            "start_time": round(seg_start, 2),
            "end_time": round(seg_end, 2),
        })

    return result


def _assign_speakers_gap_based(whisper_segments: list) -> list[dict]:
    """Fallback: basic speaker change detection based on pauses > 2 seconds."""
    result = []
    current_speaker = 1
    prev_end = 0.0

    for seg in whisper_segments:
        text = seg.text.strip()
        if not text:
            continue

        # If there's a gap > 2 seconds, assume speaker change
        gap = seg.start - prev_end
        if gap > 2.0 and prev_end > 0:
            current_speaker = (current_speaker % 2) + 1  # Toggle between Speaker 1 and 2

        result.append({
            "speaker": f"Speaker {current_speaker}",
            "text": text,
            "start_time": round(seg.start, 2),
            "end_time": round(seg.end, 2),
        })
        prev_end = seg.end

    return result
