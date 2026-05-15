import os
import re
from difflib import SequenceMatcher


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


def _normalize_token(value):
    return re.sub(r"[^\w']+", "", str(value or "").lower(), flags=re.UNICODE).strip("_'")


def _assign_lyrics_to_segments(segments, lyrics_text):
    """
    Map lyrics text to Whisper segments using TIME-PROPORTIONAL allocation.

    WHY NOT SEQUENCEMATCHER:
    Songs with repeated sections (chorus 1 == chorus 2 text) cause
    SequenceMatcher to map BOTH occurrences to the SAME Whisper segment,
    compressing the second chorus to near-zero duration. This is the root
    cause of the "second chorus rushes through in half the time" bug.

    FIX: allocate lyric words proportionally to each segment's time DURATION.
    Duration is always monotonically increasing, so chorus 2 always gets its
    own proportional word budget regardless of text repetition.
    """
    import logging
    log = logging.getLogger("whisperx_runner")

    if not lyrics_text or not segments:
        return segments

    # Extract clean lyric words — skip section labels like [Chorus]
    lyric_words = []
    for line in lyrics_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith(("embed", "you might also like")):
            continue
        if re.fullmatch(r"\[.*?\]", line):
            continue  # skip section markers entirely from injection
        line = re.sub(r"\d*embed$", "", line, flags=re.IGNORECASE).strip()
        lyric_words.extend(re.findall(r"\S+", line))

    if not lyric_words:
        return segments

    total_lyric_words = len(lyric_words)

    # Compute each segment's time duration and transcript word count
    seg_info = []
    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        duration = max(end - start, 0.0)
        tok_count = len([t for t in re.findall(r"\S+", seg.get("text", "")) if _normalize_token(t)])
        seg_info.append({"seg": seg, "duration": duration, "tok_count": tok_count})

    total_duration = sum(s["duration"] for s in seg_info) or 1.0
    total_tok = sum(s["tok_count"] for s in seg_info) or 1

    # Allocate words: 70% weight on duration (monotonic, safe for repeats)
    #                 30% weight on transcript density (handles silence gaps)
    raw_alloc = []
    for s in seg_info:
        dur_weight = s["duration"] / total_duration
        tok_weight = s["tok_count"] / total_tok
        weight = 0.7 * dur_weight + 0.3 * tok_weight
        raw_alloc.append(weight * total_lyric_words)

    # Round to integers while preserving total
    int_alloc = []
    remainder = 0.0
    for r in raw_alloc:
        frac = r + remainder
        n = int(frac)
        remainder = frac - n
        int_alloc.append(n)

    # Distribute leftover words to the longest segments first
    leftover = total_lyric_words - sum(int_alloc)
    if leftover > 0:
        order = sorted(range(len(int_alloc)), key=lambda i: seg_info[i]["duration"], reverse=True)
        for i in order[:leftover]:
            int_alloc[i] += 1

    # Ensure no text-bearing segment receives 0 words
    for i, s in enumerate(seg_info):
        if s["tok_count"] > 0 and int_alloc[i] == 0 and total_lyric_words > len(seg_info):
            donor = max(range(len(int_alloc)), key=lambda j: int_alloc[j] if j != i else -1)
            if int_alloc[donor] > 1:
                int_alloc[donor] -= 1
                int_alloc[i] = 1

    log.info(
        "_assign_lyrics_to_segments: %d lyric words across %d segments  alloc=%s",
        total_lyric_words, len(segments), int_alloc,
    )

    # Build new segments
    cursor = 0
    new_segments = []
    for i, s in enumerate(seg_info):
        count = int_alloc[i]
        chunk = lyric_words[cursor:cursor + count]
        if chunk:
            new_seg = dict(s["seg"])
            new_seg["text"] = " ".join(chunk)
            new_segments.append(new_seg)
        cursor += count

    # Safety: if any words remain, append to last segment
    if cursor < total_lyric_words:
        remaining = lyric_words[cursor:]
        if new_segments:
            new_segments[-1]["text"] = new_segments[-1]["text"] + " " + " ".join(remaining)
        else:
            last = dict(segments[-1])
            last["text"] = " ".join(remaining)
            new_segments.append(last)

    return new_segments



def align(audio_path, lyrics_text=None, language=None, vocals_path=None,
          model_size="medium", aligner="whisperx"):
    """
    Transcribe and align words to audio using WhisperX or a forced alignment engine.

    Parameters
    ----------
    audio_path : str
        Path to the original audio file.
    lyrics_text : str, optional
        Known lyrics text to improve alignment accuracy.
    language : str, optional
        Language code hint (e.g. "en", "hi").
    vocals_path : str, optional
        Path to isolated vocals stem from Demucs.
    model_size : str
        Whisper model size: "base", "small", or "medium".
    aligner : str
        Alignment backend: "whisperx" (default) or "forced" to use the built‑in forced aligner.
    """
    # Resolve alignment backend from environment if not explicitly set
    import os
    if aligner == "whisperx":
        aligner = os.getenv("FORCED_ALIGNER", "whisperx")
    else:
        # aligner argument overrides env var
        pass

    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX dependencies are not installed. Install with: pip install whisperx torch"
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

    # Pattern A: expand segment coverage to full audio duration
    audio_duration = _get_audio_duration(audio_path)
    if audio_duration:
        result["segments"] = _expand_segment_coverage(
            result.get("segments", []), audio_duration
        )

    raw_segments = [
        {
            "start": round(float(seg.get("start", 0)), 3),
            "end": round(float(seg.get("end", 0)), 3),
            "text": str(seg.get("text", "")).strip(),
        }
        for seg in result.get("segments", [])
        if seg.get("text", "").strip()
    ]

    # ---------------------------------------------------------------------
    # Forced‑alignment fallback
    # ---------------------------------------------------------------------
    if aligner != "whisperx" and lyrics_text:
        log.info("Falling back to forced‑alignment engine: %s", aligner)
        try:
            from .forced_aligner import align_lyrics
        except Exception as exc:
            log.error("Failed to import forced_aligner: %s", exc)
            raise
        # Use the forced aligner to get segment‑level timestamps
        forced_segments = align_lyrics(audio_path, lyrics_text, language=language_code)
        # Convert segment timestamps into word‑level timestamps by even distribution
        words = []
        for seg in forced_segments:
            segment_words = seg["text"].split()
            if not segment_words:
                continue
            start = seg["start"]
            end = seg["end"]
            duration = max(end - start, len(segment_words) * 0.01)
            for idx, word in enumerate(segment_words):
                word_start = round(start + (idx / len(segment_words)) * duration, 3)
                word_end = round(start + ((idx + 1) / len(segment_words)) * duration, 3)
                words.append({"word": word, "start": word_start, "end": word_end})
        return {"language": language_code, "words": words, "segments": raw_segments}

    # ---------------------------------------------------------------------
    # Regular Whisper‑X alignment path — with True Forced Alignment injection
    # Replace Whisper's guessed transcript text with the actual provided lyrics
    # before feeding into the CTC aligner. This forces the model to hunt for
    # the exact phonemes in the lyrics rather than whatever it transcribed.
    # ---------------------------------------------------------------------
    if lyrics_text:
        log.info("Injecting lyrics into segments via _assign_lyrics_to_segments...")
        result["segments"] = _assign_lyrics_to_segments(result["segments"], lyrics_text)
        log.info("Lyrics injection complete: %d segments after injection.", len(result["segments"]))

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
    missing_ts = 0
    total_ws = 0
    for segment in aligned.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            start = word.get("start")
            end = word.get("end")
            total_ws += 1
            if not text:
                continue
            if start is None or end is None:
                missing_ts += 1
                log.debug("  WORD %-20s  start=None  end=None  <- INTERPOLATED", repr(text))
                continue
            log.debug("  WORD %-20s  start=%.3f  end=%.3f  <- CTC aligned", repr(text), start, end)
            words.append({
                "word": text,
                "start": round(float(start), 3),
                "end": round(float(end), 3),
            })

    log.info(
        "Alignment complete: %d/%d words have real CTC timestamps, %d missing (will be interpolated by TTML generator).",
        len(words), total_ws, missing_ts,
    )
    if total_ws > 0 and missing_ts / total_ws > 0.3:
        log.warning(
            "%.0f%% of words lack CTC timestamps — alignment quality is poor. "
            "Segment-guided fallback will activate in ttml_generator.",
            missing_ts / total_ws * 100,
        )

    return {"language": language_code, "words": words, "segments": raw_segments}


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
