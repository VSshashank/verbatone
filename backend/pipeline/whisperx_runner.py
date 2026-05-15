import os


def _get_audio_duration(audio_path):
    """Get audio duration in seconds using librosa."""
    try:
        import librosa

        return librosa.get_duration(path=audio_path)
    except Exception:
        return None


def _expand_segment_coverage(segments, audio_duration):
    """
    If Whisper's detected segments only cover the early portion of the audio
    (common with R&B intros, slow tempo tracks), extend coverage to the full
    audio duration. This prevents lyrics from being crammed into early
    timestamps when the downstream TTML generator distributes words.

    Pattern A fix: segments bunched early in the audio.
    """
    if not segments or not audio_duration or audio_duration <= 0:
        return segments

    last_segment_end = max(
        float(seg.get("end", 0)) for seg in segments if seg.get("end") is not None
    )

    # If detected segments cover less than 80% of the audio, add a synthetic
    # tail segment so word distribution spans the full track.
    if last_segment_end < audio_duration * 0.8:
        segments = list(segments) + [
            {
                "text": "",
                "start": last_segment_end,
                "end": audio_duration,
            }
        ]

    return segments


def align(audio_path, lyrics_text=None, language=None, vocals_path=None,
          model_size="medium"):
    """
    Transcribe and align words to audio using WhisperX.

    Parameters
    ----------
    audio_path : str
        Path to the original audio file (used for duration and fallback).
    lyrics_text : str, optional
        Known lyrics text to improve alignment accuracy.
    language : str, optional
        Language code hint (e.g. "en", "hi").
    vocals_path : str, optional
        Path to isolated vocals stem from Demucs. When available, WhisperX
        aligns against the clean vocals instead of the full mix — dramatically
        more accurate for breathy/falsetto vocals (Pattern C fix).
    model_size : str
        Whisper model size: "base", "small", or "medium". Larger models are
        slower but better at detecting soft vocals. Default is "base".
    """
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX dependencies are not installed. "
            "Install them with: pip install whisperx torch"
        ) from exc

    import logging
    log = logging.getLogger("whisperx_runner")
    logging.basicConfig(level=logging.INFO)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    log.info("Loading Whisper model=%s device=%s", model_size, device)
    model = whisperx.load_model(model_size, device, compute_type=compute_type)

    # Pattern C: prefer vocals stem for alignment if available
    align_source = audio_path
    if vocals_path and os.path.exists(vocals_path):
        align_source = vocals_path
        log.info("Using vocals stem for alignment: %s", vocals_path)
    else:
        log.info("Using full mix for alignment: %s", audio_path)

    audio = whisperx.load_audio(align_source)
    result = model.transcribe(audio, language=language)
    language_code = language or result.get("language") or "en"

    raw_segments = result.get("segments", [])
    log.info(
        "Transcription complete: %d segments detected, language=%s",
        len(raw_segments), language_code,
    )
    for i, seg in enumerate(raw_segments[:10]):
        log.info(
            "  Seg %d  [%.1fs - %.1fs]  %s",
            i, seg.get("start", 0), seg.get("end", 0),
            str(seg.get("text", ""))[:80],
        )

    # Pattern A: expand segment coverage to full audio duration
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration:
        result["segments"] = _expand_segment_coverage(
            result.get("segments", []), audio_duration
        )

    # Preserve raw transcript segments — the TTML generator uses these as
    # timing guardrails when anchor matches are sparse (common in R&B).
    raw_segments = [
        {
            "start": round(float(seg.get("start", 0)), 3),
            "end": round(float(seg.get("end", 0)), 3),
            "text": str(seg.get("text", "")).strip(),
        }
        for seg in result.get("segments", [])
        if seg.get("text", "").strip()
    ]

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

    return {
        "language": language_code,
        "words": words,
        "segments": raw_segments,
    }


def transcribe(audio_path, language=None, model_size="medium"):
    """
    Pure Whisper transcription with word-level timestamps.
    Used for podcasts and speech files — no lyrics text needed.

    Parameters
    ----------
    audio_path : str
        Path to the audio file.
    language : str, optional
        Language code hint.
    model_size : str
        Whisper model size: "base", "small", or "medium".
    """
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError("WhisperX is not installed.") from exc

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    model = whisperx.load_model(model_size, device, compute_type=compute_type)
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
