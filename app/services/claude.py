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


async def generate_report(job_data: dict) -> str:
    """Build a pipeline report from real job data only — no LLM, no hallucination."""
    from app.config import get_language

    segments = json.loads(job_data.get("transcript_json") or "[]")
    translated = json.loads(job_data.get("edited_json") or job_data.get("translated_json") or "[]")
    detected_langs = json.loads(job_data.get("detected_languages_json") or "[]")
    voice_map = json.loads(job_data.get("voice_map_json") or "{}")

    total_segments = len(translated)

    # Find untranslated segments (where original == translated text)
    untranslated = []
    for i, s in enumerate(translated):
        orig = s.get("text", "").strip()
        trans = s.get("translated_text", "").strip()
        if orig == trans and orig:
            det = s.get("detected_language", {})
            lang_str = det.get("name", "Unknown") if isinstance(det, dict) else str(det)
            untranslated.append({"index": i, "text": orig[:80], "language": lang_str})

    translated_count = total_segments - len(untranslated)
    translation_pct = round(translated_count / total_segments * 100, 1) if total_segments else 0

    duration_secs = max((s.get("end_time", 0) for s in segments), default=0)
    duration_min = round(duration_secs / 60, 1)

    num_speakers = len(voice_map)
    speaker_names = ", ".join(voice_map.keys()) if voice_map else "None detected"

    target_code = job_data.get("target_language", "unknown")
    target_lang = get_language(target_code)
    target_name = target_lang["name"] if target_lang else target_code

    has_vocals = bool(job_data.get("vocals_file"))
    has_background = bool(job_data.get("background_file"))

    # --- Build the report as bullet points ---
    lines = []

    lines.append("## Summary")
    lines.append(f"- Translated **{duration_min} minutes** of audio into **{target_name}**")
    lines.append(f"- **{translated_count}** of **{total_segments}** segments translated ({translation_pct}%)")
    lines.append(f"- **{num_speakers}** speaker{'s' if num_speakers != 1 else ''} detected and voice-cloned: {speaker_names}")

    # Source languages
    if detected_langs:
        lang_parts = [f"{l['name']} ({l['percentage']}%)" for l in detected_langs]
        lines.append(f"- Source language{'s' if len(detected_langs) > 1 else ''} detected: {', '.join(lang_parts)}")

    # Source separation
    if has_vocals and has_background:
        lines.append("- Source separation ran successfully — background music/SFX will be mixed into the final audio")
    elif has_vocals:
        lines.append("- Source separation produced a vocals track (no background track available)")
    else:
        lines.append("- Source separation was skipped — full audio used for transcription")

    # Translation coverage
    if len(untranslated) == 0:
        lines.append("")
        lines.append("## Translation Coverage")
        lines.append("- All segments were translated successfully")
    else:
        lines.append("")
        lines.append("## Untranslated Segments")
        lines.append(f"- **{len(untranslated)}** segment{'s' if len(untranslated) != 1 else ''} came back unchanged (original text = translated text)")
        # Group by detected language
        by_lang: dict[str, int] = {}
        for u in untranslated:
            by_lang[u["language"]] = by_lang.get(u["language"], 0) + 1
        for lang, count in sorted(by_lang.items(), key=lambda x: -x[1]):
            lines.append(f"  - {count} segment{'s' if count != 1 else ''} in **{lang}**")
        # Show a few examples
        for u in untranslated[:5]:
            lines.append(f"  - Segment {u['index']}: \"{u['text']}...\"")
        if len(untranslated) > 5:
            lines.append(f"  - ...and {len(untranslated) - 5} more")

    # Voice cloning
    lines.append("")
    lines.append("## Voice Cloning")
    if voice_map:
        for speaker, voice_id in voice_map.items():
            lines.append(f"- **{speaker}** — cloned (voice ID: {voice_id[:12]}...)")
    else:
        lines.append("- No speakers were cloned (voice map is empty)")

    return "\n".join(lines)
