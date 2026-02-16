import logging
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger(__name__)

_separator = None


def _get_separator(output_dir: str):
    """Lazy-load the audio-separator with the best available vocal removal model."""
    global _separator
    if _separator is not None:
        _separator.output_dir = output_dir
        return _separator

    try:
        from audio_separator.separator import Separator

        logger.info("Initializing audio-separator (CPU mode for Celery fork compatibility)...")
        _separator = Separator(
            output_dir=output_dir,
            output_format="WAV",
        )
        # Force CPU mode — MPS (Metal) crashes in Celery's forked worker processes
        # with "Unable to reach MTLCompilerService" SIGABRT
        import torch
        _separator.torch_device = torch.device("cpu")
        _separator.torch_device_mps = None
        logger.info("Forced CPU mode to avoid MPS fork crash")

        # Load the best vocal separation model (BS-RoFormer, SDR 12.9)
        _separator.load_model(
            model_filename="model_bs_roformer_ep_317_sdr_12.9755.ckpt"
        )
        logger.info("audio-separator loaded with BS-RoFormer model")
        return _separator

    except Exception as e:
        logger.warning(f"Failed to initialize audio-separator: {e}")
        return None


def separate(audio_path: str, output_dir: str) -> dict[str, str]:
    """Separate vocals from music/SFX using audio-separator (UVR models).

    Returns {"vocals": "path/vocals.wav", "no_vocals": "path/instrumental.wav"}.
    The instrumental track contains ONLY music and sound effects — all speech removed.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    vocals_path = str(output_dir_path / "vocals.wav")
    instrumental_path = str(output_dir_path / "instrumental.wav")

    separator = _get_separator(output_dir)
    if separator is None:
        logger.warning("audio-separator unavailable, falling back to original audio")
        return _fallback(audio_path, vocals_path, instrumental_path)

    try:
        logger.info(f"Running source separation on {audio_path}")

        # Separate into Vocals and Instrumental stems
        output_files = separator.separate(audio_path)

        logger.info(f"Separation produced: {output_files}")

        # audio-separator returns filenames (not full paths) relative to output_dir
        # Resolve them to absolute paths
        found_vocals = None
        found_instrumental = None
        for f in output_files:
            # If the file is not an absolute path, prepend output_dir
            f_path = Path(f) if Path(f).is_absolute() else output_dir_path / f
            f_lower = f_path.stem.lower()
            if "vocal" in f_lower and "instrumental" not in f_lower:
                found_vocals = str(f_path)
            elif "instrumental" in f_lower or "no_vocal" in f_lower:
                found_instrumental = str(f_path)

        logger.info(f"Resolved: vocals={found_vocals}, instrumental={found_instrumental}")

        if not found_vocals or not found_instrumental:
            raise FileNotFoundError(
                f"Expected vocals + instrumental files, got: {output_files}"
            )

        # Move to our standard paths if they differ
        _move_if_needed(found_vocals, vocals_path)
        _move_if_needed(found_instrumental, instrumental_path)

        logger.info(f"Source separation complete: vocals={vocals_path}, "
                     f"instrumental={instrumental_path}")
        return {"vocals": vocals_path, "no_vocals": instrumental_path}

    except Exception as e:
        logger.warning(f"Source separation failed: {e}")
        return _fallback(audio_path, vocals_path, instrumental_path)


def _move_if_needed(src: str, dst: str):
    """Move a file to the destination if it's not already there."""
    import shutil
    src_path = Path(src).resolve()
    dst_path = Path(dst).resolve()
    if src_path != dst_path:
        shutil.move(str(src_path), str(dst_path))


def _fallback(
    audio_path: str, vocals_path: str, instrumental_path: str
) -> dict[str, str]:
    """Last-resort fallback when separation is completely unavailable.

    Uses the original audio for both vocals (transcription still works)
    and as the background (will be heavily attenuated during mix, so original
    speech bleeds through faintly but music/SFX is preserved).
    """
    audio = AudioSegment.from_file(audio_path)
    audio.export(vocals_path, format="wav")
    audio.export(instrumental_path, format="wav")

    logger.warning(f"Source separation unavailable — using original audio as "
                    f"fallback background. vocals={vocals_path} ({Path(vocals_path).exists()}), "
                    f"instrumental={instrumental_path} ({Path(instrumental_path).exists()})")
    return {"vocals": vocals_path, "no_vocals": instrumental_path}
