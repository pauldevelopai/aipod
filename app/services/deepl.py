import logging

from deep_translator import GoogleTranslator

from app.config import get_language

logger = logging.getLogger(__name__)


def translate_text(text: str, target_lang: str, source_lang: str | None = None) -> str:
    """Translate text using Google Translate. source_lang='auto' for auto-detect."""
    if not text.strip():
        return text

    src = source_lang if source_lang and source_lang != "auto" else "auto"
    translator = GoogleTranslator(source=src, target=target_lang)
    return translator.translate(text)


async def translate_segments(
    segments: list[dict],
    target_lang: str,
) -> list[dict]:
    """Translate all segments using Google Translate with auto-detection.
    Returns segments with 'translated_text' field."""
    translated = []
    for segment in segments:
        text = segment["text"]
        try:
            # Always use auto-detect — langdetect codes are unreliable for
            # underrepresented languages and cause Google Translate to skip them
            result = translate_text(text, target_lang, "auto")
        except Exception as e:
            logger.error(f"Google Translate failed for segment: {e}")
            result = text

        translated.append({
            **segment,
            "translated_text": result,
        })

    return translated
