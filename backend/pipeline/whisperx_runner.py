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
