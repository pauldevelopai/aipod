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


def smart_mix(
    tts_path: str,
    background_path: str,
    output_path: str,
    transcript_segments: list[dict],
    bg_volume_db: float = -12.0,
    crossfade_ms: int = 500,
) -> str:
    """Smart mix: preserve intro/outro music at full volume, mix TTS over attenuated middle.

    Uses transcript segment timestamps to detect:
    - Intro: background before first speech (full volume)
    - Middle: background during speech section (attenuated, mixed with TTS)
    - Outro: background after last speech (full volume)

    If TTS is longer/shorter than original speech, the middle background is
    looped or trimmed so the intro and outro still fit properly.
    """
    tts = AudioSegment.from_file(tts_path)
    background = AudioSegment.from_file(background_path)

    tts = ensure_stereo(tts)
    background = ensure_stereo(background)
    background = background.set_frame_rate(tts.frame_rate)

    bg_len = len(background)

    if bg_len == 0:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tts.export(output_path, format="mp3", bitrate="192k")
        logger.info("Background is empty, exporting TTS only")
        return output_path

    # Find intro/outro boundaries from original transcript timestamps
    if transcript_segments:
        first_speech_ms = int(transcript_segments[0].get("start_time", 0) * 1000)
        last_speech_ms = int(transcript_segments[-1].get("end_time", 0) * 1000)
    else:
        first_speech_ms = 0
        last_speech_ms = bg_len

    # Clamp to actual background length
    first_speech_ms = min(first_speech_ms, bg_len)
    last_speech_ms = min(last_speech_ms, bg_len)

    # Split background into three sections
    intro_bg = background[:first_speech_ms]
    middle_bg = background[first_speech_ms:last_speech_ms]
    outro_bg = background[last_speech_ms:]

    intro_len = len(intro_bg)
    middle_len = len(middle_bg)
    outro_len = len(outro_bg)
    tts_len = len(tts)

    logger.info(f"Smart mix: intro={intro_len}ms, middle_bg={middle_len}ms, "
                f"outro={outro_len}ms, tts={tts_len}ms")

    # Attenuate the middle background
    if middle_len > 0:
        middle_bg_quiet = middle_bg + bg_volume_db
    else:
        middle_bg_quiet = AudioSegment.empty()

    # Adjust middle background to match TTS duration
    if tts_len > 0 and middle_len > 0:
        if tts_len > middle_len:
            # TTS is longer than original speech — loop the middle background
            repeats = (tts_len // middle_len) + 1
            middle_bg_quiet = (middle_bg_quiet * repeats)[:tts_len]
        elif tts_len < middle_len:
            # TTS is shorter — trim middle background
            middle_bg_quiet = middle_bg_quiet[:tts_len]

    # Mix TTS with the attenuated middle background
    if len(middle_bg_quiet) > 0 and tts_len > 0:
        # Ensure same length for overlay
        mbq_len = len(middle_bg_quiet)
        if tts_len > mbq_len:
            middle_bg_quiet = middle_bg_quiet + AudioSegment.silent(
                duration=tts_len - mbq_len, frame_rate=tts.frame_rate
            )
        elif mbq_len > tts_len:
            tts = tts + AudioSegment.silent(
                duration=mbq_len - tts_len, frame_rate=tts.frame_rate
            )
        mixed_middle = tts.overlay(middle_bg_quiet)
    else:
        mixed_middle = tts

    # Stitch: intro (full volume) + mixed middle + outro (full volume)
    # Use crossfades for smooth transitions
    final = AudioSegment.empty()

    if intro_len > 0:
        final = intro_bg
        if len(mixed_middle) > 0:
            if intro_len > crossfade_ms and len(mixed_middle) > crossfade_ms:
                final = final.append(mixed_middle, crossfade=crossfade_ms)
            else:
                final = final + mixed_middle
    else:
        final = mixed_middle

    if outro_len > 0:
        if len(final) > crossfade_ms and outro_len > crossfade_ms:
            final = final.append(outro_bg, crossfade=crossfade_ms)
        else:
            final = final + outro_bg

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    final.export(output_path, format="mp3", bitrate="192k")
    logger.info(f"Smart mix complete: intro={intro_len}ms + speech={len(mixed_middle)}ms "
                f"+ outro={outro_len}ms = {len(final)}ms total, output: {output_path}")
    return output_path
