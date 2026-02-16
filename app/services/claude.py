import json
import logging

import anthropic
import openai

from app.config import settings

logger = logging.getLogger(__name__)

POLISH_SYSTEM_PROMPT = """You are an expert podcast translator. You receive original transcript segments
and their machine translations. Your job is to polish the translations to sound natural and conversational.

Rules:
- Preserve the speaker's personality and tone
- Adapt idioms and cultural references appropriately
- Maintain a conversational, podcast-friendly tone
- Keep the meaning accurate while making it sound natural
- Preserve any emotion markers like [Laughing], [Thoughtful], etc.
- Keep speaker labels and timestamps unchanged
- Return ONLY the polished translation text, nothing else"""

REPORT_SYSTEM_PROMPT = """You are a quality analyst for AiPod, a podcast translation pipeline.
You receive statistics about a completed translation job and write a clear, conversational report
for the user explaining what worked well, what had issues, and what they should know.

Write in a friendly, professional tone. Use short paragraphs. Be specific with numbers and examples.
Structure your report with these sections (use markdown):
- **Summary** — one-line overview of the job result
- **What Worked Well** — stages and aspects that performed successfully
- **Issues & Limitations** — anything that didn't work perfectly, with specifics
- **Recommendations** — actionable suggestions for better results next time

Keep it concise but thorough. Don't sugarcoat problems."""


def _llm_complete(system: str, user_message: str, max_tokens: int = 1024) -> str:
    """Call an LLM: tries Anthropic first, falls back to OpenAI."""
    # Try Anthropic
    if settings.anthropic_api_key:
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Anthropic failed: {e}")

    # Fall back to OpenAI
    if settings.openai_api_key:
        try:
            client = openai.OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI failed: {e}")

    raise RuntimeError("No LLM provider available (both Anthropic and OpenAI failed)")


async def polish_translation(
    original_text: str,
    machine_translation: str,
    source_lang_name: str,
    target_lang_name: str,
) -> str:
    """Polish a machine translation using an LLM."""
    if not machine_translation.strip():
        return machine_translation

    user_message = (
        f"Original ({source_lang_name}):\n{original_text}\n\n"
        f"Machine Translation ({target_lang_name}):\n{machine_translation}\n\n"
        f"Please provide a polished, natural-sounding {target_lang_name} translation:"
    )

    return _llm_complete(POLISH_SYSTEM_PROMPT, user_message)


async def polish_segments(
    segments: list[dict],
    target_lang_name: str,
    default_source_lang_name: str = "the original language",
) -> list[dict]:
    """Polish all translated segments. Uses per-segment detected_language when available."""
    polished = []
    for segment in segments:
        detected = segment.get("detected_language", {})
        source_name = detected.get("name") if detected.get("code", "unknown") != "unknown" else default_source_lang_name

        try:
            result = await polish_translation(
                original_text=segment["text"],
                machine_translation=segment.get("translated_text", segment["text"]),
                source_lang_name=source_name,
                target_lang_name=target_lang_name,
            )
        except Exception as e:
            logger.error(f"LLM polishing failed for segment: {e}")
            result = segment.get("translated_text", segment["text"])

        polished.append({
            **segment,
            "translated_text": result,
        })

    return polished


def _compute_report_stats(job_data: dict) -> dict:
    """Compute pipeline statistics for the report."""
    segments = json.loads(job_data.get("transcript_json") or "[]")
    translated = json.loads(job_data.get("edited_json") or job_data.get("translated_json") or "[]")
    detected_langs = json.loads(job_data.get("detected_languages_json") or "[]")
    voice_map = json.loads(job_data.get("voice_map_json") or "{}")

    total_segments = len(translated)
    untranslated = []
    for i, s in enumerate(translated):
        orig = s.get("text", "").strip()
        trans = s.get("translated_text", "").strip()
        if orig == trans and orig:
            det = s.get("detected_language", {})
            lang_str = det.get("name", "Unknown") if isinstance(det, dict) else str(det)
            untranslated.append({"index": i, "text": orig[:100], "language": lang_str})

    translated_count = total_segments - len(untranslated)
    translation_pct = round(translated_count / total_segments * 100, 1) if total_segments else 0

    duration_secs = max((s.get("end_time", 0) for s in segments), default=0)
    duration_min = round(duration_secs / 60, 1)

    return {
        "total_segments": total_segments,
        "translated_count": translated_count,
        "translation_pct": translation_pct,
        "untranslated": untranslated,
        "duration_min": duration_min,
        "detected_langs": detected_langs,
        "voice_map": voice_map,
        "target_language": job_data.get("target_language", "unknown"),
    }


async def generate_report(job_data: dict) -> str:
    """Generate a pipeline report using an LLM."""
    stats = _compute_report_stats(job_data)

    lang_summary = ", ".join(f"{l['name']} ({l['percentage']}%)" for l in stats["detected_langs"][:5])
    prompt_stats = f"""Target Language: {stats['target_language']}
Audio Duration: {stats['duration_min']} minutes
Total Segments: {stats['total_segments']}
Segments Translated: {stats['translated_count']} ({stats['translation_pct']}%)
Segments Untranslated: {len(stats['untranslated'])} ({round(100 - stats['translation_pct'], 1)}%)
Speakers: {len(stats['voice_map'])}
Detected Languages: {lang_summary}

Untranslated Segments (original text returned unchanged):
"""
    for u in stats["untranslated"][:15]:
        prompt_stats += f"  - Seg {u['index']} [{u['language']}]: \"{u['text']}\"\n"
    if not stats["untranslated"]:
        prompt_stats += "  None — all segments were translated successfully.\n"

    return _llm_complete(
        REPORT_SYSTEM_PROMPT,
        f"Please write a report for this completed translation job:\n\n{prompt_stats}",
        max_tokens=2048,
    )
