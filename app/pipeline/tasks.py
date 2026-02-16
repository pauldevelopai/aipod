import asyncio
import json
import logging
from pathlib import Path

from app.pipeline.worker import celery_app
from app.config import settings, get_language, BASE_DIR
from app.database import SessionLocal
from app.models import Job

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async function from sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _update_job(job_id: str, **kwargs):
    """Update job fields in the database."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            for key, value in kwargs.items():
                setattr(job, key, value)
            db.commit()
    finally:
        db.close()


def _get_job(job_id: str) -> dict:
    """Get job data as dict."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        return job.to_dict() if job else {}
    finally:
        db.close()


@celery_app.task(bind=True, name="aipod.run_pipeline")
def run_pipeline(self, job_id: str, start_from: int = 1):
    """Run pipeline stages 1-6.
    start_from allows resuming from a specific stage."""
    try:
        # Clear any stale error from previous run
        _update_job(job_id, error_message=None)
        job = _get_job(job_id)

        if start_from <= 1:
            # Skip if cleaned file already exists on disk
            cleaned = job.get("cleaned_file")
            if cleaned and Path(cleaned).exists():
                logger.info(f"Job {job_id}: Stage 1 skipped - cleaned file exists")
            else:
                _update_job(job_id, status="processing", current_stage=1, stage_name="Audio Cleanup (Auphonic)")
                stage_1_audio_cleanup(job_id)
        else:
            _update_job(job_id, status="processing")

        if start_from <= 2:
            job = _get_job(job_id)
            vocals = job.get("vocals_file")
            if vocals and Path(vocals).exists():
                logger.info(f"Job {job_id}: Stage 2 skipped - separation already done")
            else:
                _update_job(job_id, current_stage=2, stage_name="Source Separation (Demucs)")
                stage_2_source_separation(job_id)

        if start_from <= 3:
            job = _get_job(job_id)
            transcript = job.get("transcript_json")
            if transcript and json.loads(transcript):
                logger.info(f"Job {job_id}: Stage 3 skipped - transcript exists")
            else:
                _update_job(job_id, current_stage=3, stage_name="Transcription + Diarization (Whisper + pyannote)")
                stage_3_transcription(job_id)

                _update_job(job_id, current_stage=3, stage_name="Detecting Languages")
                stage_3b_language_detection(job_id)

        if start_from <= 4:
            job = _get_job(job_id)
            translated = job.get("translated_json")
            if translated and json.loads(translated):
                logger.info(f"Job {job_id}: Stage 4 skipped - translation exists")
            else:
                _update_job(job_id, current_stage=4, stage_name="Translation (Google + Claude)")
                stage_4_translation(job_id)

        # Use translated_json as edited_json (no human review step)
        job = _get_job(job_id)
        if not job.get("edited_json"):
            _update_job(job_id, edited_json=job.get("translated_json"))

        if start_from <= 5:
            _update_job(job_id, current_stage=5, stage_name="Voice Cloning (ElevenLabs)")
            stage_5_voice_cloning(job_id)

        if start_from <= 6:
            _update_job(job_id, current_stage=6, stage_name="Speech Generation + Mix (ElevenLabs TTS)")
            stage_6_speech_generation(job_id)

        # Generate pipeline report
        _update_job(job_id, stage_name="Generating Report")
        generate_report(job_id)

        _update_job(job_id, status="completed", stage_name="Complete")
        logger.info(f"Job {job_id}: Pipeline completed")

    except Exception as e:
        logger.exception(f"Pipeline failed for job {job_id}")
        _update_job(job_id, status="failed", error_message=str(e))
        raise


@celery_app.task(bind=True, name="aipod.resume_pipeline")
def resume_pipeline(self, job_id: str):
    """Resume the pipeline from stage 6 (after editor review)."""
    run_pipeline(job_id, start_from=6)


def stage_1_audio_cleanup(job_id: str):
    """Stage 1: Clean audio using Auphonic."""
    from app.services import auphonic

    job = _get_job(job_id)
    original_file = job["original_file"]
    cleaned_path = str(BASE_DIR / settings.output_dir / job_id / "cleaned.mp3")

    uuid = _run_async(auphonic.process_audio(original_file, cleaned_path))

    _update_job(job_id, cleaned_file=cleaned_path, auphonic_production_id=uuid)
    logger.info(f"Job {job_id}: Stage 1 complete - audio cleaned")


def stage_2_source_separation(job_id: str):
    """Stage 2: Separate vocals from music/SFX using Demucs."""
    from app.services.separation import separate

    job = _get_job(job_id)
    cleaned_file = job["cleaned_file"]
    separation_dir = str(BASE_DIR / settings.output_dir / job_id / "separation")

    result = separate(cleaned_file, separation_dir)

    _update_job(
        job_id,
        vocals_file=result["vocals"],
        background_file=result["no_vocals"],
    )
    logger.info(f"Job {job_id}: Stage 2 complete - source separation done")


def stage_3_transcription(job_id: str):
    """Stage 3: Transcribe audio using Whisper + pyannote diarization."""
    from app.services.transcribe import transcribe
    from app.services.diarize import diarize

    job = _get_job(job_id)
    # Use vocals track if available, otherwise fall back to cleaned file
    audio_file = job.get("vocals_file") or job["cleaned_file"]

    # Run pyannote diarization first (returns None if unavailable)
    diarization_segments = diarize(audio_file)

    # Transcribe with diarization info
    segments = transcribe(audio_file, diarization_segments=diarization_segments)

    _update_job(
        job_id,
        transcript_json=json.dumps(segments),
    )
    logger.info(f"Job {job_id}: Stage 3 complete - {len(segments)} segments transcribed"
                f" ({'pyannote' if diarization_segments else 'gap-based'} diarization)")


def stage_3b_language_detection(job_id: str):
    """Stage 3b: Detect language for each transcript segment."""
    from app.services.language import detect_segments_languages, summarize_detected_languages

    job = _get_job(job_id)
    segments = json.loads(job["transcript_json"])

    # Tag each segment with its detected language
    segments_with_langs = detect_segments_languages(segments)

    # Build a summary of all detected languages
    summary = summarize_detected_languages(segments_with_langs)

    lang_names = ", ".join(f"{l['name']} ({l['percentage']}%)" for l in summary)
    logger.info(f"Job {job_id}: Detected languages: {lang_names}")

    _update_job(
        job_id,
        transcript_json=json.dumps(segments_with_langs),
        detected_languages_json=json.dumps(summary),
    )


def stage_4_translation(job_id: str):
    """Stage 4: Translate using Google Translate (per-segment source lang) + Claude polish."""
    from app.services import deepl, claude

    job = _get_job(job_id)
    segments = json.loads(job["transcript_json"])
    target_lang = get_language(job["target_language"])

    # Google Translate uses ISO codes (e.g. "en", "fr")
    target_code = target_lang["code"] if target_lang else job["target_language"]
    target_name = target_lang["name"] if target_lang else job["target_language"]

    # Pass 1: Google Translate raw translation (uses per-segment detected_language)
    translated = _run_async(deepl.translate_segments(segments, target_code))

    # Pass 2: Claude polishing (uses per-segment detected_language names)
    polished = _run_async(claude.polish_segments(translated, target_name))

    _update_job(job_id, translated_json=json.dumps(polished))
    logger.info(f"Job {job_id}: Stage 4 complete - {len(polished)} segments translated and polished")


def stage_5_voice_cloning(job_id: str):
    """Stage 5: Clone voices for each speaker using ElevenLabs.
    Uses fingerprint cache to reuse voices for recurring speakers."""
    from app.services import elevenlabs, audio
    from app.services import fingerprint

    job = _get_job(job_id)
    original_file = job["original_file"]
    segments = json.loads(job["transcript_json"])
    samples_dir = str(BASE_DIR / settings.output_dir / job_id / "speaker_samples")

    # Extract speaker samples
    speaker_samples = audio.extract_best_speaker_samples(original_file, segments, samples_dir)

    # Clone each voice (with fingerprint cache)
    voice_map = {}
    for speaker, sample_path in speaker_samples.items():
        # Compute speaker embedding
        embedding = fingerprint.compute_embedding(sample_path)

        if embedding is not None:
            # Check fingerprint cache
            cached = fingerprint.find_matching_profile(embedding)
            if cached:
                logger.info(f"Job {job_id}: Reusing cached voice for {speaker} "
                            f"(matched profile '{cached.name}')")
                voice_map[speaker] = cached.elevenlabs_voice_id
                continue

        # No cache match — clone via ElevenLabs
        voice_id = _run_async(elevenlabs.clone_voice(f"aipod_{job_id[:8]}_{speaker}", sample_path))
        voice_map[speaker] = voice_id

        # Cache the new voice profile
        if embedding is not None:
            fingerprint.create_profile(
                name=speaker,
                embedding=embedding,
                voice_id=voice_id,
                sample_file=sample_path,
            )

    _update_job(job_id, voice_map_json=json.dumps(voice_map))
    logger.info(f"Job {job_id}: Stage 5 complete - {len(voice_map)} voices cloned")


def stage_6_speech_generation(job_id: str):
    """Stage 6: Generate TTS for each segment, stitch, and mix with background."""
    from app.services import elevenlabs, audio as audio_service

    job = _get_job(job_id)
    edited_json = job.get("edited_json") or job.get("translated_json")
    segments = json.loads(edited_json)
    voice_map = json.loads(job["voice_map_json"])
    segments_dir = str(BASE_DIR / settings.output_dir / job_id / "tts_segments")
    Path(segments_dir).mkdir(parents=True, exist_ok=True)

    segment_files = []
    for i, segment in enumerate(segments):
        speaker = segment.get("speaker", "Speaker")
        text = segment.get("translated_text", segment.get("text", ""))
        voice_id = voice_map.get(speaker)

        if not voice_id or not text.strip():
            continue

        out_path = str(Path(segments_dir) / f"segment_{i:04d}.mp3")
        _run_async(elevenlabs.text_to_speech(text, voice_id, out_path))
        segment_files.append(out_path)

    logger.info(f"Job {job_id}: {len(segment_files)} TTS segments generated, stitching...")

    # Stitch all segments into TTS output
    tts_path = str(BASE_DIR / settings.output_dir / job_id / "tts_stitched.mp3")
    audio_service.stitch_segments(segment_files, tts_path)

    # Mix with background track if available
    background_file = job.get("background_file")
    final_path = str(BASE_DIR / settings.output_dir / job_id / "final.mp3")

    if background_file and Path(background_file).exists():
        logger.info(f"Job {job_id}: Mixing TTS with background audio")
        audio_service.mix_with_background(tts_path, background_file, final_path, bg_volume_db=-12.0)
    else:
        # No background — just use the stitched TTS as final
        logger.info(f"Job {job_id}: No background track, using TTS as final output")
        Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        Path(tts_path).rename(final_path)

    _update_job(job_id, output_file=final_path)
    logger.info(f"Job {job_id}: Stage 6 complete - final audio ready")


def generate_report(job_id: str):
    """Generate a pipeline quality report using Claude."""
    from app.services import claude

    job = _get_job(job_id)
    report = _run_async(claude.generate_report(job))
    _update_job(job_id, report_json=json.dumps({"report": report}))
    logger.info(f"Job {job_id}: Report generated")
