import logging
from collections import Counter

from langdetect import detect, detect_langs, LangDetectException

from app.config import SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# Map langdetect codes to our internal codes
_LANGDETECT_MAP = {lang["code"]: lang for lang in SUPPORTED_LANGUAGES}
# langdetect uses some different codes
_CODE_ALIASES = {
    "zh-cn": "zh", "zh-tw": "zh",
    "pt": "pt",
    "no": "nb",
    "tl": "fil",
    "sw": "sw",
}


def _normalize_code(code: str) -> str:
    """Normalize a langdetect code to our internal code."""
    code = code.lower().split("-")[0] if "-" not in _CODE_ALIASES.get(code.lower(), "") else code.lower()
    return _CODE_ALIASES.get(code, code)


def detect_segment_language(text: str) -> dict:
    """Detect the language of a text segment.
    Returns {"code": "en", "name": "English", "confidence": 0.99}."""
    if not text or not text.strip():
        return {"code": "unknown", "name": "Unknown", "confidence": 0.0}

    try:
        results = detect_langs(text)
        if not results:
            return {"code": "unknown", "name": "Unknown", "confidence": 0.0}

        top = results[0]
        code = _normalize_code(top.lang)
        lang = _LANGDETECT_MAP.get(code)

        return {
            "code": code,
            "name": lang["name"] if lang else code.upper(),
            "confidence": round(top.prob, 3),
        }
    except LangDetectException:
        return {"code": "unknown", "name": "Unknown", "confidence": 0.0}


def detect_segments_languages(segments: list[dict]) -> list[dict]:
    """Detect language for each segment, adding 'detected_language' field.
    Returns updated segments."""
    result = []
    for segment in segments:
        text = segment.get("text", "")
        detection = detect_segment_language(text)
        result.append({
            **segment,
            "detected_language": detection,
        })
    return result


def summarize_detected_languages(segments: list[dict]) -> list[dict]:
    """Summarize all detected languages across segments.
    Returns a list of {"code", "name", "count", "percentage"} sorted by frequency."""
    counts = Counter()
    names = {}
    for seg in segments:
        det = seg.get("detected_language", {})
        code = det.get("code", "unknown")
        if code != "unknown":
            counts[code] += 1
            names[code] = det.get("name", code)

    total = sum(counts.values()) or 1
    summary = []
    for code, count in counts.most_common():
        summary.append({
            "code": code,
            "name": names.get(code, code),
            "count": count,
            "percentage": round(count / total * 100, 1),
        })
    return summary
