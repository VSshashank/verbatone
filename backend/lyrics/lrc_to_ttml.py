"""
LRC → TTML converter.

For non-Indian tracks: produces line-level <p> elements (no child spans) —
LRC gives us only line timestamps, so the whole line highlights at once.

For Indian language tracks (include_phonetics=True): splits each line into
words, distributes timestamps evenly within the line duration, and adds
nested phonetic spans for the romanization toggle.
"""
import logging
import re
from html import escape

log = logging.getLogger(__name__)

_LRC_LINE_RE = re.compile(r"^\[(\d{1,2}):(\d{2})\.(\d{2,3})\]\s*(.*)")
_SKIP_RE = re.compile(r"^[♪♫\s]*$|^\s*$")


def _parse_lrc(lrc_string):
    entries = []
    for raw in lrc_string.splitlines():
        m = _LRC_LINE_RE.match(raw.strip())
        if not m:
            continue
        minutes, seconds = int(m.group(1)), int(m.group(2))
        frac = m.group(3)
        text = m.group(4).strip()
        frac_s = int(frac) / (100.0 if len(frac) == 2 else 1000.0)
        start = minutes * 60 + seconds + frac_s
        if not text or _SKIP_RE.match(text):
            continue
        entries.append((round(start, 3), text))
    return entries


def parse_lrc_to_lines(lrc_string):
    """
    Parse LRC string into structured line objects for hybrid alignment.

    Returns list of:
      {"start": float, "end": float, "text": str, "lyric_words": [str]}
    end = next line's start - 0.05s (or start + 5.0s for last line).
    Skips instrumental/empty lines.
    """
    entries = _parse_lrc(lrc_string)
    lines = []
    for index, (start, text) in enumerate(entries):
        if index + 1 < len(entries):
            end = max(start + 0.05, entries[index + 1][0] - 0.05)
        else:
            end = start + 5.0
        lines.append({
            "start": start,
            "end": round(end, 3),
            "text": text,
            "lyric_words": re.findall(r"\S+", text),
        })
    return lines


def _secs_to_ttml(seconds):
    seconds = max(float(seconds), 0.0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _romanize(word, language):
    """Romanize a single word using phonetics.py — returns original on failure."""
    try:
        from pipeline.phonetics import romanize_word
        return romanize_word(word, language)
    except Exception:
        return word


def _word_spans(text, start, end, language, include_phonetics):
    """
    Split a lyric line into word-level <span> elements with evenly-distributed
    timestamps.  If include_phonetics, adds nested primary + phonetic spans.
    """
    words = text.split()
    if not words:
        return ""

    dur = max(end - start, len(words) * 0.08)
    step = dur / len(words)
    parts = []
    for i, word in enumerate(words):
        ws = round(start + i * step, 3)
        we = round(start + (i + 1) * step, 3)
        b = _secs_to_ttml(ws)
        e = _secs_to_ttml(we)
        safe = escape(word)
        if include_phonetics:
            rom = escape(_romanize(word, language))
            parts.append(
                f'        <span begin="{b}" end="{e}">'
                f'<span style="default">{safe}</span>'
                f'<span style="phonetic">{rom}</span>'
                f"</span>"
            )
        else:
            parts.append(f'        <span begin="{b}" end="{e}">{safe}</span>')
    return "\n".join(parts)


def lrc_to_ttml(lrc_string, language="en", include_phonetics=False):
    """
    Convert an LRC string to a TTML document.

    Parameters
    ----------
    lrc_string : str
    language : str
        BCP-47 language code.
    include_phonetics : bool
        When True (Indian languages), creates word-level spans with romanized
        phonetic text so the phonetic toggle works even for LRCLIB tracks.

    Returns
    -------
    str  — valid TTML XML.
    """
    language = language or "en"
    entries = _parse_lrc(lrc_string)
    log.info("lrc_to_ttml: %d lines, phonetics=%s, lang=%s", len(entries), include_phonetics, language)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<tt xml:lang="{escape(language)}" xmlns="http://www.w3.org/ns/ttml"'
        ' xmlns:tts="http://www.w3.org/ns/ttml#styling"'
        ' data-sync-source="lrclib">',
        "  <head><styling>",
        '    <style xml:id="default" tts:color="white" tts:fontSize="120%"/>',
        '    <style xml:id="active"  tts:color="yellow" tts:fontWeight="bold"/>',
        '    <style xml:id="phonetic" tts:color="#94a3b8" tts:fontSize="75%"/>',
        "  </styling></head>",
        "  <body><div>",
    ]

    for index, (start, text) in enumerate(entries):
        if index + 1 < len(entries):
            end = max(start + 0.05, entries[index + 1][0] - 0.05)
        else:
            end = start + 5.0

        b = _secs_to_ttml(start)
        e = _secs_to_ttml(end)
        safe_text = escape(text, quote=True)

        if include_phonetics:
            spans = _word_spans(text, start, end, language, include_phonetics=True)
            out.append(
                f'    <p begin="{b}" end="{e}" data-kind="lyric" data-text="{safe_text}">\n'
                f"{spans}\n    </p>"
            )
        else:
            # Plain line-level paragraph — no child spans
            out.append(
                f'    <p begin="{b}" end="{e}" data-kind="lyric" data-text="{safe_text}">'
                f"{safe_text}</p>"
            )

    out.extend(["  </div></body>", "</tt>"])
    return "\n".join(out)


def merged_lines_to_ttml(merged_lines, language="en", include_phonetics=False):
    """
    Convert merged Genius+LRCLIB lines to TTML (line-level, same shape as lrc_to_ttml).

    Parameters
    ----------
    merged_lines : list
        Output of merge_genius_lrclib()["lines"] — dicts with kind, text, start, end.
    """
    language = language or "en"
    lines = merged_lines or []
    log.info("merged_lines_to_ttml: %d lines, lang=%s", len(lines), language)

    lyric_starts = [
        float(line["start"])
        for line in lines
        if line.get("kind") == "lyric" and line.get("start") is not None
    ]

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<tt xml:lang="{escape(language)}" xmlns="http://www.w3.org/ns/ttml"'
        ' xmlns:tts="http://www.w3.org/ns/ttml#styling"'
        ' data-sync-source="genius+lrclib">',
        "  <head><styling>",
        '    <style xml:id="default" tts:color="white" tts:fontSize="120%"/>',
        '    <style xml:id="active"  tts:color="yellow" tts:fontWeight="bold"/>',
        '    <style xml:id="phonetic" tts:color="#94a3b8" tts:fontSize="75%"/>',
        "  </styling></head>",
        "  <body><div>",
    ]

    fallback_start = lyric_starts[0] if lyric_starts else 0.0
    lyric_cursor = 0

    for line in lines:
        kind = line.get("kind", "lyric")
        text = str(line.get("text", "") or "").strip()
        safe_text = escape(text, quote=True)

        if kind == "gap":
            out.append('    <p data-kind="gap" data-text=""/>')
            continue

        if kind == "label":
            out.append(f'    <p data-kind="label" data-text="{safe_text}"/>')
            continue

        if kind != "lyric" or not text:
            continue

        if line.get("start") is not None:
            start = float(line["start"])
        elif lyric_cursor < len(lyric_starts):
            start = lyric_starts[lyric_cursor]
        else:
            start = fallback_start

        if line.get("end") is not None:
            end = float(line["end"])
        else:
            end = start + 5.0

        lyric_cursor += 1

        b = _secs_to_ttml(start)
        e = _secs_to_ttml(end)

        if include_phonetics:
            spans = _word_spans(text, start, end, language, include_phonetics=True)
            out.append(
                f'    <p begin="{b}" end="{e}" data-kind="lyric" data-text="{safe_text}">\n'
                f"{spans}\n    </p>"
            )
        else:
            out.append(
                f'    <p begin="{b}" end="{e}" data-kind="lyric" data-text="{safe_text}">'
                f"{escape(text)}</p>"
            )

    out.extend(["  </div></body>", "</tt>"])
    return "\n".join(out)
