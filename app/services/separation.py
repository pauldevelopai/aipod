import logging
import shutil
import subprocess
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger(__name__)


def separate(audio_path: str, output_dir: str) -> dict[str, str]:
    """Run Demucs htdemucs model to separate vocals from music/SFX.

    Returns {"vocals": "path/vocals.wav", "no_vocals": "path/no_vocals.wav"}.
    Falls back gracefully: original as vocals, silence as background.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    vocals_path = str(output_dir / "vocals.wav")
    no_vocals_path = str(output_dir / "no_vocals.wav")

    try:
        # Run Demucs CLI — outputs stems into output_dir/htdemucs/<track_name>/
        track_name = Path(audio_path).stem
        cmd = [
            "python", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", str(output_dir),
            audio_path,
        ]
        logger.info(f"Running Demucs: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode != 0:
            logger.warning(f"Demucs failed (rc={result.returncode}): {result.stderr}")
            raise RuntimeError(result.stderr)

        # Demucs outputs to: output_dir/htdemucs/<track_name>/vocals.wav and no_vocals.wav
        demucs_dir = output_dir / "htdemucs" / track_name
        demucs_vocals = demucs_dir / "vocals.wav"
        demucs_no_vocals = demucs_dir / "no_vocals.wav"

        if not demucs_vocals.exists():
            raise FileNotFoundError(f"Demucs vocals not found at {demucs_vocals}")

        # Move background first (before vocals is moved out of demucs_dir)
        if demucs_no_vocals.exists():
            shutil.move(str(demucs_no_vocals), no_vocals_path)
        else:
            # If --two-stems produced other stem names, combine them
            _create_background_from_stems(demucs_dir, no_vocals_path, exclude="vocals")

        # Move vocals
        shutil.move(str(demucs_vocals), vocals_path)

        logger.info(f"Source separation complete: vocals={vocals_path}, background={no_vocals_path}")
        return {"vocals": vocals_path, "no_vocals": no_vocals_path}

    except Exception as e:
        logger.warning(f"Source separation failed, using fallback: {e}")
        return _fallback(audio_path, vocals_path, no_vocals_path)


def _create_background_from_stems(
    stems_dir: Path, output_path: str, exclude: str = "vocals"
) -> str:
    """Combine all non-vocal stems (drums, bass, other) into one background track."""
    combined = None
    for stem_file in stems_dir.glob("*.wav"):
        if exclude in stem_file.stem:
            continue
        stem = AudioSegment.from_file(str(stem_file))
        if combined is None:
            combined = stem
        else:
            combined = combined.overlay(stem)

    if combined is None:
        # No stems found — create silence matching vocals duration
        vocals = AudioSegment.from_file(str(stems_dir / f"{exclude}.wav"))
        combined = AudioSegment.silent(duration=len(vocals))

    combined.export(output_path, format="wav")
    return output_path


def _fallback(
    audio_path: str, vocals_path: str, no_vocals_path: str
) -> dict[str, str]:
    """Fallback: use original as vocals and silence as background."""
    audio = AudioSegment.from_file(audio_path)

    # Use original audio as vocals
    audio.export(vocals_path, format="wav")

    # Create silence for background
    silence = AudioSegment.silent(duration=len(audio))
    silence.export(no_vocals_path, format="wav")

    return {"vocals": vocals_path, "no_vocals": no_vocals_path}
