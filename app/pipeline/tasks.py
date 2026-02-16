import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

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


def _log_stage(job_id: str, message: str):
    """Append a timestamped log entry to the job's stage_log (visible in UI)."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        existing = json.loads(job.stage_log) if job.stage_log else []
        existing.append({
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "msg": message,
        })
        job.stage_log = json.dumps(existing)
        db.commit()
    finally:
        db.close()
    logger.info(f"Job {job_id}: {message}")


@celery_app.task(bind=True, name="aipod.run_pipeline")
def run_pipeline(self, job_id: str, start_from: int = 1):
    """Run pipeline stages 1-6.
    start_from allows resuming from a specific stage."""
    try:
        # Clear any stale error and log from previous run
        _update_job(job_id, error_message=None, stage_log=None)
        _log_stage(job_id, f"Pipeline starting from stage {start_from}")
        job = _get_job(job_id)

        if start_from <= 1:
            cleaned = job.get("cleaned_file")
            if cleaned and Path(cleaned).exists():
                _log_stage(job_id, "Stage 1 skipped — cleaned audio already exists")
            else:
                _update_job(job_id, status="processing", current_stage=1, stage_name="Audio Cleanup (Auphonic)")
                _log_stage(job_id, "Stage 1: Uploading to Auphonic for audio cleanup...")
                stage_1_audio_cleanup(job_id)
                _log_stage(job_id, "Stage 1 complete — audio cleaned")
        else:
            _update_job(job_id, status="processing")

        if start_from <= 2:
            job = _get_job(job_id)
            vocals = job.get("vocals_file")
            if vocals and Path(vocals).exists():
                _log_stage(job_id, "Stage 2 skipped — vocals/background already separated")
            else:
                _update_job(job_id, current_stage=2, stage_name="Source Separation")
                _log_stage(job_id, "Stage 2: Separating vocals from music/SFX (MDX-NET ONNX, CPU)...")
                stage_2_source_separation(job_id)
                _log_stage(job_id, "Stage 2 complete — vocals and background tracks ready")

        if start_from <= 3:
            job = _get_job(job_id)
            transcript = job.get("transcript_json")
            if transcript and json.loads(transcript):
                _log_stage(job_id, "Stage 3 skipped — transcript already exists")
            else:
                _update_job(job_id, current_stage=3, stage_name="Transcription + Diarization (Whisper + pyannote)")
                _log_stage(job_id, "Stage 3: Running speaker diarization + Whisper transcription...")
                stage_3_transcription(job_id)

                _update_job(job_id, current_stage=3, stage_name="Detecting Languages")
                _log_stage(job_id, "Stage 3b: Detecting languages in transcript segments...")
                stage_3b_language_detection(job_id)
                _log_stage(job_id, "Stage 3 complete — transcript + languages ready")

        if start_from <= 4:
            job = _get_job(job_id)
            translated = job.get("translated_json")
            if translated and json.loads(translated):
                _log_stage(job_id, "Stage 4 skipped — translation already exists")
            else:
                _update_job(job_id, current_stage=4, stage_name="Translation (Google + Claude)")
                _log_stage(job_id, "Stage 4: Translating with Google Translate + Claude polish...")
                stage_4_translation(job_id)
                _log_stage(job_id, "Stage 4 complete — translation polished")

        # Use translated_json as edited_json (no human review step)
        job = _get_job(job_id)
        if not job.get("edited_json"):
            _update_job(job_id, edited_json=job.get("translated_json"))

        if start_from <= 5:
            job = _get_job(job_id)
            voice_map = job.get("voice_map_json")
            if voice_map and json.loads(voice_map):
                _log_stage(job_id, "Stage 5 skipped — voice clones already cached")
            else:
                _update_job(job_id, current_stage=5, stage_name="Voice Cloning (ElevenLabs)")
                _log_stage(job_id, "Stage 5: Extracting speaker samples and cloning voices...")
                stage_5_voice_cloning(job_id)
                _log_stage(job_id, "Stage 5 complete — voices cloned")

        if start_from <= 6:
            _update_job(job_id, current_stage=6, stage_name="Speech Generation + Mix (ElevenLabs TTS)")
            _log_stage(job_id, "Stage 6: Generating speech for each segment...")
            stage_6_speech_generation(job_id)
            _log_stage(job_id, "Stage 6 complete — final audio mixed")

        # Generate pipeline report
        _update_job(job_id, stage_name="Generating Report")
        _log_stage(job_id, "Generating pipeline quality report...")
        generate_report(job_id)

        _update_job(job_id, status="completed", stage_name="Complete")
        _log_stage(job_id, "Pipeline completed successfully")

    except SoftTimeLimitExceeded:
        logger.warning(f"Pipeline timed out for job {job_id}")
        _log_stage(job_id, "FAILED: Task exceeded time limit — please retry")
        _update_job(job_id, status="failed", error_message="Task exceeded time limit — please retry")
    except Exception as e:
        logger.exception(f"Pipeline failed for job {job_id}")
        _log_stage(job_id, f"FAILED: {e}")
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

    _log_stage(job_id, f"Uploading {Path(original_file).name} to Auphonic...")
    uuid = _run_async(auphonic.process_audio(original_file, cleaned_path))

    _update_job(job_id, cleaned_file=cleaned_path, auphonic_production_id=uuid)
    _log_stage(job_id, f"Auphonic production {uuid} complete, cleaned audio saved")


def stage_2_source_separation(job_id: str):
    """Stage 2: Separate vocals from music/SFX using audio-separator."""
    import threading
    from app.services.separation import separate

    job = _get_job(job_id)
    cleaned_file = job["cleaned_file"]
    separation_dir = str(BASE_DIR / settings.output_dir / job_id / "separation")

    _log_stage(job_id, "Running MDX-NET ONNX source separation (this may take a few minutes)...")

    # Heartbeat: touch the DB every 30s so the UI doesn't think the worker crashed
    stop_heartbeat = threading.Event()
    def heartbeat():
        mins = 0
        while not stop_heartbeat.wait(30):
            mins += 0.5
            _log_stage(job_id, f"Source separation still running ({mins:.0f}m elapsed)...")
    hb_thread = threading.Thread(target=heartbeat, daemon=True)
    hb_thread.start()

    try:
        result = separate(cleaned_file, separation_dir)
    finally:
        stop_heartbeat.set()
        hb_thread.join(timeout=2)

    _update_job(
        job_id,
        vocals_file=result["vocals"],
        background_file=result["no_vocals"],
    )
    vocals_exists = Path(result["vocals"]).exists()
    bg_exists = Path(result["no_vocals"]).exists()
    _log_stage(job_id, f"Separation done: vocals={vocals_exists}, background={bg_exists}")


def stage_3_transcription(job_id: str):
    """Stage 3: Transcribe audio using Whisper + pyannote diarization."""
    from app.services.transcribe import transcribe
    from app.services.diarize import diarize

    job = _get_job(job_id)
    audio_file = job.get("vocals_file") or job["cleaned_file"]

    _log_stage(job_id, "Running pyannote speaker diarization...")
    diarization_segments = diarize(audio_file)
    if diarization_segments:
        speakers = set(s.get("speaker") for s in diarization_segments)
        _log_stage(job_id, f"Diarization found {len(speakers)} speakers, {len(diarization_segments)} segments")
    else:
        _log_stage(job_id, "pyannote unavailable, will use gap-based speaker detection")

    _log_stage(job_id, "Running Whisper transcription...")
    segments = transcribe(audio_file, diarization_segments=diarization_segments)

    _update_job(job_id, transcript_json=json.dumps(segments))
    method = "pyannote" if diarization_segments else "gap-based"
    _log_stage(job_id, f"Transcribed {len(segments)} segments ({method} diarization)")


def stage_3b_language_detection(job_id: str):
    """Stage 3b: Detect language for each transcript segment."""
    from app.services.language import detect_segments_languages, summarize_detected_languages

    job = _get_job(job_id)
    segments = json.loads(job["transcript_json"])

    segments_with_langs = detect_segments_languages(segments)
    summary = summarize_detected_languages(segments_with_langs)

    lang_names = ", ".join(f"{l['name']} ({l['percentage']}%)" for l in summary)
    _log_stage(job_id, f"Detected languages: {lang_names}")

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

    target_code = target_lang["code"] if target_lang else job["target_language"]
    target_name = target_lang["name"] if target_lang else job["target_language"]

    _log_stage(job_id, f"Pass 1: Google Translate → {target_name} ({len(segments)} segments)...")
    translated = _run_async(deepl.translate_segments(segments, target_code))

    _log_stage(job_id, f"Pass 2: Claude polishing {len(translated)} translated segments...")
    polished = _run_async(claude.polish_segments(translated, target_name))

    _update_job(job_id, translated_json=json.dumps(polished))
    _log_stage(job_id, f"Translation complete: {len(polished)} segments → {target_name}")


def stage_5_voice_cloning(job_id: str):
    """Stage 5: Clone voices for each speaker using ElevenLabs.
    Uses fingerprint cache to reuse voices for recurring speakers."""
    from app.services import elevenlabs, audio
    from app.services import fingerprint

    job = _get_job(job_id)
    original_file = job["original_file"]
    segments = json.loads(job["transcript_json"])
    samples_dir = str(BASE_DIR / settings.output_dir / job_id / "speaker_samples")

    _log_stage(job_id, "Extracting best audio sample for each speaker...")
    speaker_samples = audio.extract_best_speaker_samples(original_file, segments, samples_dir)
    _log_stage(job_id, f"Found {len(speaker_samples)} speakers, checking fingerprint cache...")

    voice_map = {}
    for speaker, sample_path in speaker_samples.items():
        embedding = fingerprint.compute_embedding(sample_path)

        if embedding is not None:
            cached = fingerprint.find_matching_profile(embedding)
            if cached:
                _log_stage(job_id, f"Reusing cached voice for {speaker} (matched '{cached.name}')")
                voice_map[speaker] = cached.elevenlabs_voice_id
                continue

        _log_stage(job_id, f"Cloning voice for {speaker} via ElevenLabs...")
        voice_id = _run_async(elevenlabs.clone_voice(f"aipod_{job_id[:8]}_{speaker}", sample_path))
        voice_map[speaker] = voice_id

        if embedding is not None:
            fingerprint.create_profile(
                name=speaker,
                embedding=embedding,
                voice_id=voice_id,
                sample_file=sample_path,
            )

    _update_job(job_id, voice_map_json=json.dumps(voice_map))
    _log_stage(job_id, f"Voice cloning complete: {len(voice_map)} voices ready")


def stage_6_speech_generation(job_id: str):
    """Stage 6: Generate TTS for each segment, stitch, and smart-mix with background."""
    from app.services import elevenlabs, audio as audio_service

    job = _get_job(job_id)
    edited_json = job.get("edited_json") or job.get("translated_json")
    segments = json.loads(edited_json)
    voice_map = json.loads(job["voice_map_json"])
    segments_dir = str(BASE_DIR / settings.output_dir / job_id / "tts_segments")
    Path(segments_dir).mkdir(parents=True, exist_ok=True)

    total_segments = sum(1 for s in segments if voice_map.get(s.get("speaker", "")) and s.get("translated_text", s.get("text", "")).strip())
    _log_stage(job_id, f"Generating TTS for {total_segments} segments via ElevenLabs...")

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

        if len(segment_files) % 10 == 0:
            _log_stage(job_id, f"TTS progress: {len(segment_files)}/{total_segments} segments done")

    _log_stage(job_id, f"All {len(segment_files)} TTS segments generated, stitching audio...")

    tts_path = str(BASE_DIR / settings.output_dir / job_id / "tts_stitched.mp3")
    audio_service.stitch_segments(segment_files, tts_path)

    transcript_segments = json.loads(job.get("transcript_json") or "[]")
    background_file = job.get("background_file")
    final_path = str(BASE_DIR / settings.output_dir / job_id / "final.mp3")

    if background_file and Path(background_file).exists():
        _log_stage(job_id, "Smart mixing TTS with background audio (preserving intro/outro)...")
        audio_service.smart_mix(
            tts_path, background_file, final_path,
            transcript_segments=transcript_segments,
            bg_volume_db=-12.0,
        )
        _log_stage(job_id, "Smart mix complete — background music preserved with intro/outro")
    else:
        _log_stage(job_id, "No background track available — using TTS-only output")
        Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(tts_path, final_path)

    _update_job(job_id, output_file=final_path)


def generate_report(job_id: str):
    """Generate a pipeline quality report from real job data."""
    from app.services import claude

    job = _get_job(job_id)
    report = _run_async(claude.generate_report(job))
    _update_job(job_id, report_json=json.dumps({"report": report}))
