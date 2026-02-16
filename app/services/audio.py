import logging
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger(__name__)


def ensure_stereo(audio: AudioSegment) -> AudioSegment:
    """Convert mono audio to stereo if needed."""
    if audio.channels == 1:
        audio = audio.set_channels(2)
    return audio


def extract_speaker_sample(
    audio_path: str,
    start_ms: int,
    end_ms: int,
    output_path: str,
    min_duration_ms: int = 30000,
    max_duration_ms: int = 60000,
) -> str:
    """Extract a speaker sample from the audio file for voice cloning.
    Ensures the sample is between min_duration_ms and max_duration_ms."""
    audio = AudioSegment.from_file(audio_path)

    # Clamp the duration
    duration = end_ms - start_ms
    if duration < min_duration_ms:
        # Extend if possible
        end_ms = min(start_ms + min_duration_ms, len(audio))
    if duration > max_duration_ms:
        end_ms = start_ms + max_duration_ms

    sample = audio[start_ms:end_ms]
    sample = ensure_stereo(sample)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    sample.export(output_path, format="mp3")
    return output_path


def extract_best_speaker_samples(
    audio_path: str,
    segments: list[dict],
    output_dir: str,
) -> dict[str, str]:
    """Extract the best audio sample for each unique speaker.
    Returns {speaker_label: sample_file_path}."""
    audio = AudioSegment.from_file(audio_path)
    speaker_segments: dict[str, list[dict]] = {}

    for seg in segments:
        speaker = seg.get("speaker", "Speaker")
        if speaker not in speaker_segments:
            speaker_segments[speaker] = []
        speaker_segments[speaker].append(seg)

    samples = {}
    for speaker, segs in speaker_segments.items():
        # Sort by duration (longest first) to get the best sample
        segs.sort(key=lambda s: (s.get("end_time", 0) - s.get("start_time", 0)), reverse=True)

        # Accumulate segments until we have 30-60 seconds
        combined = AudioSegment.empty()
        for seg in segs:
            start_ms = int(seg.get("start_time", 0) * 1000)
            end_ms = int(seg.get("end_time", 0) * 1000)
            if end_ms > start_ms:
                combined += audio[start_ms:end_ms]
            if len(combined) >= 60000:
                break

        if len(combined) < 5000:
            logger.warning(f"Speaker {speaker} has very short audio ({len(combined)}ms), using what's available")

        # Trim to max 60 seconds
        combined = combined[:60000]
        combined = ensure_stereo(combined)

        out_path = str(Path(output_dir) / f"speaker_{speaker.replace(' ', '_')}.mp3")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        combined.export(out_path, format="mp3")
        samples[speaker] = out_path

    return samples


def stitch_segments(
    segment_files: list[str],
    output_path: str,
    crossfade_ms: int = 100,
    sample_rate: int = 44100,
) -> str:
    """Stitch multiple audio segment files together with crossfades."""
    if not segment_files:
        raise ValueError("No segment files to stitch")

    combined = AudioSegment.from_file(segment_files[0])
    combined = ensure_stereo(combined)
    combined = combined.set_frame_rate(sample_rate)

    for seg_file in segment_files[1:]:
        segment = AudioSegment.from_file(seg_file)
        segment = ensure_stereo(segment)
        segment = segment.set_frame_rate(sample_rate)

        if crossfade_ms > 0 and len(combined) > crossfade_ms and len(segment) > crossfade_ms:
            combined = combined.append(segment, crossfade=crossfade_ms)
        else:
            combined += segment

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    combined.export(output_path, format="mp3", bitrate="192k")
    return output_path


def normalize_audio(audio_path: str, target_dbfs: float = -16.0) -> AudioSegment:
    """Normalize audio to a target loudness."""
    audio = AudioSegment.from_file(audio_path)
    change_in_dbfs = target_dbfs - audio.dBFS
    return audio.apply_gain(change_in_dbfs)


def mix_with_background(
    tts_path: str,
    background_path: str,
    output_path: str,
    bg_volume_db: float = -12.0,
) -> str:
    """Mix TTS audio with background track (music/SFX).

    The background is attenuated by bg_volume_db. If the background is shorter
    than the TTS, it is looped. If longer, it is trimmed.
    """
    tts = AudioSegment.from_file(tts_path)
    background = AudioSegment.from_file(background_path)

    # Attenuate background
    background = background + bg_volume_db

    # Handle duration mismatch
    tts_len = len(tts)
    bg_len = len(background)

    if bg_len == 0:
        # Empty background — nothing to mix, just export TTS as-is
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tts.export(output_path, format="mp3", bitrate="192k")
        logger.info(f"Background is empty, exporting TTS only: {output_path}")
        return output_path

    if bg_len < tts_len:
        # Loop background to match TTS duration
        loops_needed = (tts_len // bg_len) + 1
        background = background * loops_needed

    # Trim background to match TTS length
    background = background[:tts_len]

    # Ensure same channels and sample rate
    background = background.set_channels(tts.channels)
    background = background.set_frame_rate(tts.frame_rate)

    # Overlay background under TTS
    mixed = tts.overlay(background)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mixed.export(output_path, format="mp3", bitrate="192k")
    logger.info(f"Mixed TTS ({tts_len}ms) with background, output: {output_path}")
    return output_path
