import re


def _split_into_words(text):
    return re.findall(r"\S+", text or "")


def _override_segments_with_lyrics(segments, lyrics_text):
    """
    Replace the text in Whisper segments with words from the provided lyrics.
    Distributes lyrics words across segments proportionally by original word count.
    This ensures forced alignment runs against the correct lyrics text rather than
    Whisper's (often inaccurate) transcription of sung audio.
    """
    lyric_words = _split_into_words(lyrics_text)
    if not lyric_words:
        return segments

    total_whisper_words = sum(
        len(_split_into_words(seg.get("text", ""))) for seg in segments
    )
    if total_whisper_words == 0:
        return segments

    overridden = []
    lyric_cursor = 0
    for seg in segments:
        seg_word_count = len(_split_into_words(seg.get("text", "")))
        proportion = seg_word_count / total_whisper_words
        take = max(1, round(proportion * len(lyric_words)))
        chunk = lyric_words[lyric_cursor : lyric_cursor + take]
        lyric_cursor += take
        overridden.append({**seg, "text": " ".join(chunk)})

    # Append any remaining lyric words to the last segment
    if lyric_cursor < len(lyric_words):
        remainder = " ".join(lyric_words[lyric_cursor:])
        if overridden:
            overridden[-1] = {
                **overridden[-1],
                "text": overridden[-1]["text"] + " " + remainder,
            }
        else:
            overridden.append({"text": remainder, "start": 0, "end": 0})

    return overridden


def align(audio_path, lyrics_text=None, language=None):
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX dependencies are not installed. "
            "Install them with: pip install whisperx torch"
        ) from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model("base", device, compute_type=compute_type)
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, language=language)
    language_code = language or result.get("language") or "en"

    # Override transcription with provided lyrics before alignment
    if lyrics_text and lyrics_text.strip():
        result["segments"] = _override_segments_with_lyrics(
            result.get("segments", []), lyrics_text
        )

    align_model, metadata = whisperx.load_align_model(
        language_code=language_code,
        device=device,
    )
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )

    words = []
    for segment in aligned.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            start = word.get("start")
            end = word.get("end")
            if not text or start is None or end is None:
                continue
            words.append(
                {
                    "word": text,
                    "start": round(float(start), 3),
                    "end": round(float(end), 3),
                }
            )

    return {"language": language_code, "words": words}


def transcribe(audio_path, language=None):
    """
    Pure Whisper transcription with word-level timestamps.
    Used for podcasts and speech files — no lyrics text needed.
    """
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError("WhisperX is not installed.") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model("base", device, compute_type=compute_type)
    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, language=language)
    language_code = language or result.get("language") or "en"

    align_model, metadata = whisperx.load_align_model(
        language_code=language_code, device=device
    )
    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )

    words = []
    for segment in aligned.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            start = word.get("start")
            end = word.get("end")
            if not text or start is None or end is None:
                continue
            words.append(
                {
                    "word": text,
                    "start": round(float(start), 3),
                    "end": round(float(end), 3),
                }
            )

    return {"language": language_code, "words": words}
