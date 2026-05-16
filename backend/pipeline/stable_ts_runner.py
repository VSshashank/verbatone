import logging
import os

log = logging.getLogger("stable_ts_runner")

MODEL_CACHE = {}

try:
    import stable_whisper

    _STABLE_TS_AVAILABLE = True
except ImportError:
    stable_whisper = None
    _STABLE_TS_AVAILABLE = False


def _get_model(model_size):
    if model_size not in MODEL_CACHE:
        log.info("Loading stable-ts model=%s", model_size)
        MODEL_CACHE[model_size] = stable_whisper.load_model(model_size)
    return MODEL_CACHE[model_size]


def _resolve_align_source(audio_path, vocals_path):
    if vocals_path and os.path.exists(vocals_path):
        return vocals_path, "vocals"
    return audio_path, "full"


def _word_from_entry(entry):
    if hasattr(entry, "word"):
        text = str(entry.word or "").strip()
        start = getattr(entry, "start", None)
        end = getattr(entry, "end", None)
    else:
        text = str(entry.get("word", "")).strip()
        start = entry.get("start")
        end = entry.get("end")
    return text, start, end


def _extract_words_and_segments(result):
    words = []
    segments = []

    segments_source = getattr(result, "segments", None)
    if segments_source is None:
        data = result.to_dict() if hasattr(result, "to_dict") else {}
        segments_source = data.get("segments", [])

    for segment in segments_source:
        if hasattr(segment, "start"):
            seg_start = float(segment.start)
            seg_end = float(segment.end)
            seg_text = str(getattr(segment, "text", "") or "").strip()
            seg_words = getattr(segment, "words", None) or []
        else:
            seg_start = float(segment.get("start", 0))
            seg_end = float(segment.get("end", seg_start))
            seg_text = str(segment.get("text", "") or "").strip()
            seg_words = segment.get("words") or []

        if seg_text:
            segments.append({
                "start": round(seg_start, 3),
                "end": round(seg_end, 3),
                "text": seg_text,
            })

        for entry in seg_words:
            text, start, end = _word_from_entry(entry)
            if not text:
                continue
            words.append({
                "word": text,
                "start": None if start is None else round(float(start), 3),
                "end": None if end is None else round(float(end), 3),
            })

    return words, segments


def _postprocess_words(words):
    before = len(words)
    filtered = []
    dropped_none = 0
    dropped_short = 0

    for word in words:
        start = word.get("start")
        end = word.get("end")
        if start is None or end is None:
            dropped_none += 1
            continue
        duration = float(end) - float(start)
        if duration < 0.01:
            dropped_short += 1
            continue
        filtered.append(word)

    filtered.sort(key=lambda item: float(item["start"]))
    log.info(
        "stable-ts post-process: kept %d/%d words (dropped %d missing ts, %d <0.01s)",
        len(filtered), before, dropped_none, dropped_short,
    )
    return filtered


def _alignment_stats(words, raw_count):
    valid = len(words)
    pct = (valid / raw_count * 100) if raw_count else 0.0
    log.info(
        "stable-ts align: %d words with valid timestamps (%.0f%% of %d raw)",
        valid, pct, raw_count,
    )


def align(
    audio_path,
    lyrics_text=None,
    language=None,
    vocals_path=None,
    model_size="medium",
):
    """
    Align lyrics to audio using stable-ts forced alignment.

    Returns the same shape as whisperx_runner.align():
      {"words": [{"word", "start", "end"}, ...], "segments": [...], "language": str}
    """
    if not _STABLE_TS_AVAILABLE:
        from pipeline.whisperx_runner import align as whisperx_align

        log.warning("stable-ts not available, falling back to WhisperX")
        return whisperx_align(
            audio_path,
            lyrics_text=lyrics_text,
            language=language,
            vocals_path=vocals_path,
            model_size=model_size,
        )

    if not lyrics_text or not str(lyrics_text).strip():
        raise ValueError("lyrics_text is required for stable-ts alignment")

    model = _get_model(model_size)
    align_source, audio_kind = _resolve_align_source(audio_path, vocals_path)
    log.info(
        "stable-ts align: model=%s, audio=%s, source=%s",
        model_size, audio_kind, align_source,
    )

    # align() is word-level by default; word_level is not a valid kwarg here.
    align_language = language or "en"
    align_kwargs = {
        "language": align_language,
        "original_split": True,
        "verbose": False,
    }

    def _run_align(text):
        return model.align(align_source, text, **align_kwargs)

    try:
        result = _run_align(lyrics_text)
    except Exception as exc:
        log.warning("stable-ts align() failed (%s) — transcribe then re-align", exc)
        transcribe_kwargs = {"verbose": False}
        if language:
            transcribe_kwargs["language"] = language
        transcribed = model.transcribe(align_source, **transcribe_kwargs)
        detected_language = language or getattr(transcribed, "language", None) or "en"
        align_kwargs["language"] = detected_language
        result = _run_align(lyrics_text)

    detected_language = language or getattr(result, "language", None) or "en"
    raw_words, segments = _extract_words_and_segments(result)
    raw_count = len(raw_words)
    words = _postprocess_words(raw_words)
    _alignment_stats(words, raw_count)

    log.info(
        "stable-ts align: %d words, model=%s, audio=%s",
        len(words), model_size, audio_kind,
    )

    return {
        "language": detected_language,
        "words": words,
        "segments": segments,
    }
