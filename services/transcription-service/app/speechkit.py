from __future__ import annotations

import httpx
import json
import logging
import re
from pathlib import Path
from uuid import UUID

from .config import get_settings
from .iam import get_iam_token


log = logging.getLogger("transcription-service.speechkit")


_DURATION_RE = re.compile(r"^(?P<sec>\d+)(?:\.(?P<frac>\d+))?s$")
_SUMMARIZATION_RUNTIME_DISABLED = False


def _duration_to_ms(value: object) -> int:
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        return int(float(value) * 1000)

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0

        try:
            return int(float(raw) * 1000)
        except ValueError:
            pass

        match = _DURATION_RE.match(raw)
        if match:
            sec = int(match.group("sec"))
            frac = match.group("frac") or ""
            frac_ms = int((frac + "000")[:3]) if frac else 0
            return sec * 1000 + frac_ms

    raise ValueError(f"Unsupported duration format: {value!r}")


def _speaker_from_chunk(chunk: dict, words: list[dict]) -> str | None:
    for key in ("speakerLabel", "speakerTag", "speaker", "channelTag", "channel"):
        value = chunk.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    if words:
        first_word = words[0]
        for key in ("speakerLabel", "speakerTag", "speaker", "channelTag", "channel"):
            value = first_word.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return None


def _should_send_audio_channel_count(source_file_name: str | None) -> bool:
    if not source_file_name:
        return False
    ext = Path(source_file_name).suffix.lower()
    return ext in {".lpcm", ".pcm", ".raw"}


def _build_headers(*, include_content_type: bool, include_folder_id: bool) -> dict[str, str]:
    s = get_settings()
    headers = {"Authorization": f"Bearer {get_iam_token()}"}
    if include_content_type:
        headers["Content-Type"] = "application/json"
    if include_folder_id:
        if not s.speechkit_folder_id:
            raise ValueError("SPEECHKIT_FOLDER_ID is required for SpeechKit v3")
        headers["x-folder-id"] = s.speechkit_folder_id
    return headers


def _container_audio_type(source_file_name: str | None) -> str | None:
    if not source_file_name:
        return None
    ext = Path(source_file_name).suffix.lower()
    mapping = {
        ".wav": "WAV",
        ".ogg": "OGG_OPUS",
        ".opus": "OGG_OPUS",
        ".mp3": "MP3",
    }
    return mapping.get(ext)


def _is_mp3(source_file_name: str | None) -> bool:
    if not source_file_name:
        return False
    return Path(source_file_name).suffix.lower() == ".mp3"


def _submit_v2(audio_uri: str, language: str, source_file_name: str | None = None) -> str:
    s = get_settings()
    headers = _build_headers(include_content_type=True, include_folder_id=False)
    specification: dict[str, object] = {
        "languageCode": language,
        "model": s.speechkit_model,
        "rawResults": s.speechkit_raw_results,
        "literatureText": s.speechkit_literature_text,
        "profanityFilter": s.speechkit_profanity_filter,
    }
    if _should_send_audio_channel_count(source_file_name):
        specification["audioChannelCount"] = s.speechkit_audio_channel_count

    body = {
        "config": {
            "specification": specification
        },
        "audio": {"uri": audio_uri},
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(s.speechkit_long_running_url, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    op_id = data.get("id")
    if not op_id:
        raise ValueError("SpeechKit operation id missing")
    return str(op_id)


def _submit_v3(
    audio_uri: str,
    language: str,
    source_file_name: str | None = None,
    speaker_labeling_enabled: bool | None = None,
    llm_rules: list[dict] | None = None,
) -> str:
    global _SUMMARIZATION_RUNTIME_DISABLED

    s = get_settings()
    headers = _build_headers(include_content_type=True, include_folder_id=True)

    model: dict[str, object] = {
        "model": s.speechkit_model,
        "languageRestriction": {
            "restrictionType": "WHITELIST",
            "languageCode": [language],
        },
        "textNormalization": {
            "textNormalization": "TEXT_NORMALIZATION_ENABLED"
            if s.speechkit_text_normalization_enabled
            else "TEXT_NORMALIZATION_DISABLED",
            "phoneFormattingMode": "PHONE_FORMATTING_MODE_DISABLED",
            "profanityFilter": s.speechkit_profanity_filter,
            "literatureText": s.speechkit_literature_text,
        },
    }

    container_type = _container_audio_type(source_file_name)
    if container_type:
        model["audioFormat"] = {
            "containerAudio": {
                "containerAudioType": container_type,
            }
        }

    requested_labeling = s.speechkit_speaker_labeling_enabled if speaker_labeling_enabled is None else speaker_labeling_enabled
    if requested_labeling and _is_mp3(source_file_name):
        requested_labeling = False

    summarization_payload = _build_summarization_payload(llm_rules or [])

    def _build_body(enable_speaker_labeling: bool, include_summarization: bool) -> dict:
        body = {
            "uri": audio_uri,
            "recognitionModel": model,
            "speakerLabeling": {
                "speakerLabeling": "SPEAKER_LABELING_ENABLED" if enable_speaker_labeling else "SPEAKER_LABELING_DISABLED"
            },
        }

        if include_summarization and summarization_payload is not None:
            body["summarization"] = summarization_payload
        return body

    def _is_mono_only_error(resp: httpx.Response) -> bool:
        if resp.status_code != 400:
            return False
        raw_text = resp.text.lower()
        if "speaker labeling is only for mono-channel audio files" in raw_text:
            return True
        try:
            payload = resp.json()
        except Exception:
            return False
        message = str(payload.get("message", "")).lower()
        if not message:
            message = str(payload.get("error", "")).lower()
        return "speaker labeling is only for mono-channel audio files" in message

    def _summarization_error_kind(resp: httpx.Response) -> str | None:
        if resp.status_code < 400:
            return None
        error_text = resp.text.lower()
        try:
            payload = resp.json()
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            error_text = f"{error_text} {str(payload.get('message', '')).lower()} {str(payload.get('error', '')).lower()}"

        if "summarization" not in error_text:
            return None
        if "access to language models denied for summarization" in error_text:
            return "access_denied"
        return "other"

    use_summarization = summarization_payload is not None
    speaker_labeling_active = bool(requested_labeling)

    with httpx.Client(timeout=30.0) as client:
        def _submit_once() -> httpx.Response:
            return client.post(
                s.speechkit_v3_recognize_file_async_url,
                json=_build_body(speaker_labeling_active, use_summarization),
                headers=headers,
            )

        resp = _submit_once()

        if speaker_labeling_active and _is_mono_only_error(resp):
            speaker_labeling_active = False
            resp = _submit_once()

        summarization_error = _summarization_error_kind(resp)
        if use_summarization and summarization_error:
            if summarization_error == "access_denied":
                if not _SUMMARIZATION_RUNTIME_DISABLED:
                    log.warning(
                        "SpeechKit summarization access denied. Disabling summarization for current runtime and retrying without it."
                    )
                _SUMMARIZATION_RUNTIME_DISABLED = True
            else:
                log.warning("SpeechKit summarization failed. Retrying recognition submit without summarization.")

            use_summarization = False
            resp = _submit_once()

            if speaker_labeling_active and _is_mono_only_error(resp):
                speaker_labeling_active = False
                resp = _submit_once()

        if resp.status_code >= 400:
            log.error("SpeechKit v3 submit failed status=%s body=%s", resp.status_code, resp.text[:1200])

        resp.raise_for_status()
        data = resp.json()

    op_id = data.get("id")
    if not op_id:
        raise ValueError("SpeechKit v3 operation id missing")
    return str(op_id)


def submit_long_running_recognition(
    audio_uri: str,
    language: str,
    source_file_name: str | None = None,
    speaker_labeling_enabled: bool | None = None,
    llm_rules: list[dict] | None = None,
) -> str:
    s = get_settings()
    if s.speechkit_api_version.lower() == "v3":
        return _submit_v3(
            audio_uri,
            language,
            source_file_name,
            speaker_labeling_enabled=speaker_labeling_enabled,
            llm_rules=llm_rules,
        )
    return _submit_v2(audio_uri, language, source_file_name)


def get_operation(operation_id: str) -> dict:
    s = get_settings()
    headers = _build_headers(include_content_type=False, include_folder_id=s.speechkit_api_version.lower() == "v3")
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{s.speechkit_operation_url}/{operation_id}", headers=headers)
        resp.raise_for_status()
        return resp.json()


def _parse_json_sequence(raw: str) -> list[dict]:
    decoder = json.JSONDecoder()
    idx = 0
    parsed: list[dict] = []
    n = len(raw)

    while idx < n:
        while idx < n and raw[idx].isspace():
            idx += 1
        if idx >= n:
            break
        try:
            obj, next_idx = decoder.raw_decode(raw, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            parsed.append(obj)
        idx = next_idx

    if parsed:
        return parsed

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            parsed.append(obj)
    return parsed


def _coerce_matched_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes", "да", "matched", "присутствует", "present"}:
        return True
    if text in {"false", "0", "no", "нет", "absent", "отсутствует", "not_matched"}:
        return False
    return False


def _get_v3_recognition_events(operation_id: str) -> list[dict]:
    s = get_settings()
    headers = _build_headers(include_content_type=False, include_folder_id=True)
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(s.speechkit_v3_get_recognition_url, params={"operation_id": operation_id}, headers=headers)
        resp.raise_for_status()
        return _parse_json_sequence(resp.text)


def _ms_to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return 0
        return int(float(raw))
    return 0


def _split_v3_words_into_chunks(words: list[dict]) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    if not words:
        return chunks

    chunk_words: list[str] = []
    chunk_start = 0
    chunk_end = 0
    prev_end = 0

    for idx, word in enumerate(words):
        text = str(word.get("text", "")).strip()
        if not text:
            continue

        start_ms = _ms_to_int(word.get("startTimeMs"))
        end_ms = _ms_to_int(word.get("endTimeMs"))

        if not chunk_words:
            chunk_start = start_ms
            chunk_end = end_ms
            prev_end = end_ms
            chunk_words.append(text)
            continue

        gap_ms = max(0, start_ms - prev_end)
        split_by_gap = gap_ms >= 900
        split_by_len = len(chunk_words) >= 18

        if split_by_gap or split_by_len:
            chunks.append((chunk_start, chunk_end, " ".join(chunk_words).strip()))
            chunk_words = [text]
            chunk_start = start_ms
            chunk_end = end_ms
            prev_end = end_ms
            continue

        chunk_words.append(text)
        chunk_end = end_ms
        prev_end = end_ms

        if idx == len(words) - 1:
            chunks.append((chunk_start, chunk_end, " ".join(chunk_words).strip()))

    if chunk_words and (not chunks or chunks[-1][0] != chunk_start or chunks[-1][1] != chunk_end):
        chunks.append((chunk_start, chunk_end, " ".join(chunk_words).strip()))
    return chunks


def _normalize_segments_v2(operation_payload: dict) -> dict:
    response = operation_payload.get("response", {})
    chunks = response.get("chunks", [])
    segments: list[dict] = []
    full_parts: list[str] = []

    idx = 0
    for chunk in chunks:
        alternatives = chunk.get("alternatives", [])
        if not alternatives:
            continue
        alt = alternatives[0]
        text = str(alt.get("text", "")).strip()
        if not text:
            continue
        words = alt.get("words", [])
        start_ms = _duration_to_ms(words[0].get("startTime", 0)) if words else 0
        end_ms = _duration_to_ms(words[-1].get("endTime", 0)) if words else start_ms
        speaker_label = _speaker_from_chunk(chunk, words)
        segments.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
                "speaker_label": speaker_label,
                "confidence": float(alt.get("confidence", 0.0)) if alt.get("confidence") is not None else None,
                "segment_order": idx,
            }
        )
        full_parts.append(text)
        idx += 1

    return {
        "full_text": " ".join(full_parts).strip(),
        "segments": segments,
        "llm_rule_matches": [],
    }


def _normalize_segments_v3(events: list[dict]) -> dict:
    segments: list[dict] = []
    full_parts: list[str] = []
    seen_keys: set[tuple[int, int, str | None, str]] = set()
    idx = 0

    for event in events:
        result = event.get("result", event)
        if not isinstance(result, dict):
            continue

        channel = result.get("channelTag")
        if channel is None:
            channel = result.get("channel_tag")
        speaker_label = str(channel) if channel is not None else None

        updates: list[dict] = []

        final_refinement = result.get("finalRefinement")
        if isinstance(final_refinement, dict):
            normalized_text = final_refinement.get("normalizedText")
            if isinstance(normalized_text, dict):
                updates.append(normalized_text)

        final_update = result.get("final")
        if isinstance(final_update, dict):
            updates.append(final_update)

        for update in updates:
            alternatives = update.get("alternatives")
            if not isinstance(alternatives, list) or not alternatives:
                continue
            alt = alternatives[0]
            text = str(alt.get("text", "")).strip()
            if not text:
                continue
            words = alt.get("words")

            chunks: list[tuple[int, int, str]] = []
            if isinstance(words, list) and words:
                chunks = _split_v3_words_into_chunks(words)

            if not chunks:
                start_ms = _ms_to_int(alt.get("startTimeMs"))
                end_ms = _ms_to_int(alt.get("endTimeMs"))
                if (start_ms == 0 and end_ms == 0) and isinstance(words, list) and words:
                    start_ms = _ms_to_int(words[0].get("startTimeMs"))
                    end_ms = _ms_to_int(words[-1].get("endTimeMs"))
                chunks = [(start_ms, end_ms, text)]

            confidence = alt.get("confidence")
            for start_ms, end_ms, chunk_text in chunks:
                key = (start_ms, end_ms, speaker_label, chunk_text)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                segments.append(
                    {
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "text": chunk_text,
                        "speaker_label": speaker_label,
                        "confidence": float(confidence) if confidence is not None else None,
                        "segment_order": idx,
                    }
                )
                full_parts.append(chunk_text)
                idx += 1

    segments_sorted = sorted(
        segments,
        key=lambda item: (
            int(item.get("start_ms", 0)),
            int(item.get("end_ms", 0)),
            str(item.get("speaker_label") or ""),
        ),
    )

    full_parts_sorted: list[str] = []
    for i, segment in enumerate(segments_sorted):
        segment["segment_order"] = i
        text = str(segment.get("text", "")).strip()
        if text:
            full_parts_sorted.append(text)

    return {
        "full_text": " ".join(full_parts_sorted).strip(),
        "segments": segments_sorted,
        "llm_rule_matches": _extract_llm_rule_matches(events),
    }


def _build_rule_instruction(rule: dict) -> str:
    """Build transport-oriented instruction for SpeechKit summarization property."""
    rule_id = str(rule.get("id") or "").strip()
    prompt = str(rule.get("prompt") or "").strip()
    kind = str(rule.get("label_kind") or "FLAG").upper()
    allowed_labels: list[dict] = rule.get("allowed_labels") or []
    allowed_values = [str(ld.get("name") or "").strip() for ld in allowed_labels if str(ld.get("name") or "").strip()]
    allowed_values_line = ""
    if kind == "FLAG" and allowed_values:
        allowed_values_line = (
            f"Если matched=true, value_text должен быть одним из allowed_values: {allowed_values}. "
            f"Не придумывай значения вне списка.\n"
        )

    return (
        "Ты анализируешь транскрипт строго по пользовательскому правилу.\n"
        "Не переопределяй и не дополняй правило своими критериями.\n"
        f"kind: {kind}\n"
        f"user_rule: {prompt}\n"
        f"rule_id: {rule_id}\n"
        "Верни ТОЛЬКО валидный JSON без markdown и пояснений.\n"
        "Допустимые поля ответа: matched, value_text, comment, rule_id.\n"
        "Формат JSON: "
        '{"rule_id":"<rule_id>","matched":true/false,"value_text":string|null,"comment":string|null}\n'
        "Требования:\n"
        "- JSON должен быть валидным.\n"
        "- Если по правилу нет срабатывания: matched=false.\n"
        "- Если matched=true, заполни comment кратко.\n"
        "- Не добавляй поля, которых нет в контракте.\n"
        f"{allowed_values_line}"
        "- rule_id должен быть равен переданному rule_id."
    )


def _build_summarization_payload(llm_rules: list[dict]) -> dict | None:
    s = get_settings()
    if _SUMMARIZATION_RUNTIME_DISABLED:
        return None
    if not s.speechkit_summarization_enabled:
        return None
    if not s.speechkit_summarization_model_uri:
        return None
    if not llm_rules:
        return None

    properties: list[dict] = []
    for rule in llm_rules:
        rule_id = str(rule.get("id") or "").strip()
        prompt = str(rule.get("prompt") or "").strip()
        if not rule_id or not prompt:
            continue

        instruction = _build_rule_instruction(rule)
        properties.append({"instruction": instruction, "jsonObject": True})

    if not properties:
        return None

    return {
        "modelUri": s.speechkit_summarization_model_uri,
        "properties": properties,
    }


def _parse_summarization_response(raw_response: object) -> dict | None:
    """Parse one summarization result item into a dict, stripping markdown fences."""
    if isinstance(raw_response, dict):
        return raw_response
    raw = str(raw_response or "").strip()
    if not raw:
        return None
    # strip ```json ... ``` fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:]
        raw = "\n".join(inner)
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def _extract_llm_rule_matches(events: list[dict]) -> list[dict]:
    matches: list[dict] = []
    seen: set[str] = set()

    for event in events:
        payload = event.get("result", event)
        if not isinstance(payload, dict):
            continue

        summarization = payload.get("summarization")
        if not isinstance(summarization, dict):
            continue

        results = summarization.get("results")
        if not isinstance(results, list):
            continue

        for item in results:
            if not isinstance(item, dict):
                continue
            parsed = _parse_summarization_response(item.get("response"))
            if not parsed:
                continue

            raw_rule_id = parsed.get("rule_id")
            rule_id = str(raw_rule_id or "").strip()
            if rule_id.lower() in {"null", "none", "undefined"}:
                rule_id = ""
            try:
                rule_id = str(UUID(rule_id)) if rule_id else ""
            except ValueError:
                rule_id = ""

            if not rule_id:
                fallback_rule_id = item.get("propertyName") or item.get("property_name")
                fallback_rule_id_str = str(fallback_rule_id or "").strip()
                if fallback_rule_id_str.lower() in {"null", "none", "undefined"}:
                    fallback_rule_id_str = ""
                try:
                    rule_id = str(UUID(fallback_rule_id_str)) if fallback_rule_id_str else ""
                except ValueError:
                    rule_id = ""

            if not rule_id or rule_id in seen:
                continue
            seen.add(rule_id)

            value_text_raw = str(parsed.get("value_text") or "").strip()
            value_text = value_text_raw or None
            comment_raw = str(parsed.get("comment") or "").strip()
            comment = comment_raw or None

            matches.append(
                {
                    "rule_id": rule_id,
                    "label_id": None,
                    "label_value": None,
                    "matched": _coerce_matched_flag(parsed.get("matched", False)),
                    "value_number": None,
                    "value_text": value_text,
                    "comment": comment,
                }
            )

    return matches


def _ensure_default_unmatched_for_missing_rules(matches: list[dict], llm_rules: list[dict]) -> list[dict]:
    """Guarantee one result per enabled rule, even if summarization omitted it.

    This prevents "disappearing" rules in UI and allows showing unmatched reasons.
    """
    by_rule: dict[str, dict] = {}
    for match in matches:
        rule_id = str(match.get("rule_id") or "").strip()
        if not rule_id:
            continue
        by_rule[rule_id] = match

    merged: list[dict] = list(matches)
    for rule in llm_rules:
        rule_id = str(rule.get("id") or "").strip()
        if not rule_id or rule_id in by_rule:
            continue

        allowed_labels = rule.get("allowed_labels") or []
        default_label_id = None
        default_label_value = None
        if isinstance(allowed_labels, list) and allowed_labels:
            first = allowed_labels[0] or {}
            default_label_id = str(first.get("id") or "").strip() or None
            default_label_value = str(first.get("name") or "").strip() or None
        if str(rule.get("label_kind") or "").upper() == "COMMENT":
            default_label_id = None
            default_label_value = str(rule.get("name") or "").strip() or None

        merged.append(
            {
                "rule_id": rule_id,
                "label_id": default_label_id,
                "label_value": default_label_value,
                "matched": False,
                "value_number": None,
                "value_text": None,
                "comment": "Модель не вернула результат по правилу",
            }
        )

    return merged


def extract_llm_rule_matches_from_v3(operation_id: str) -> list[dict]:
    events = _get_v3_recognition_events(operation_id)
    return _extract_llm_rule_matches(events)


def normalize_segments(operation_payload: dict, operation_id: str | None = None) -> dict:
    s = get_settings()
    if s.speechkit_api_version.lower() == "v3":
        if not operation_id:
            raise ValueError("operation_id is required to fetch SpeechKit v3 recognition result")
        events = _get_v3_recognition_events(operation_id)
        return _normalize_segments_v3(events)
    return _normalize_segments_v2(operation_payload)


def normalize_segments_with_rules(
    operation_payload: dict,
    llm_rules: list[dict],
    operation_id: str | None = None,
) -> dict:
    normalized = normalize_segments(operation_payload, operation_id=operation_id)
    matches = normalized.get("llm_rule_matches", [])
    if not isinstance(matches, list):
        matches = []
    normalized["llm_rule_matches"] = _ensure_default_unmatched_for_missing_rules(matches, llm_rules)
    return normalized
