"""
Merge Genius lyrics text with LRCLIB synced timestamps (line-level).
Uses only stdlib difflib — no extra dependencies.
"""
import logging
import re
from difflib import SequenceMatcher

from lyrics.lrc_to_ttml import parse_lrc_to_lines

log = logging.getLogger(__name__)

_LABEL_RE = re.compile(r"^\[.*?\]$")


def _normalize_line(text):
    return re.sub(r"[^\w']+", "", str(text or "").lower(), flags=re.UNICODE).strip("_'")


def _parse_genius_lines(genius_text):
    lines = []
    previous_gap = False

    for raw in (genius_text or "").splitlines():
        cleaned = raw.strip()
        if not cleaned:
            if lines and not previous_gap:
                lines.append({"kind": "gap", "text": "", "start": None, "end": None})
                previous_gap = True
            continue

        lowered = cleaned.lower()
        if lowered.startswith(("embed", "you might also like")):
            continue

        cleaned = re.sub(r"\d*embed$", "", cleaned, flags=re.IGNORECASE).strip()
        if not cleaned:
            continue

        if _LABEL_RE.fullmatch(cleaned):
            lines.append({"kind": "label", "text": cleaned, "start": None, "end": None})
        else:
            lines.append({"kind": "lyric", "text": cleaned, "start": None, "end": None})
        previous_gap = False

    while lines and lines[0]["kind"] == "gap":
        lines.pop(0)
    while lines and lines[-1]["kind"] == "gap":
        lines.pop()

    return lines


def merge_genius_lrclib(genius_text, lrc_synced):
    """
    Align Genius line text to LRCLIB line timestamps.

    Returns
    -------
    dict with keys:
      lines — list of {kind, text, start, end} suitable for merged_lines_to_ttml()
      match_rate — fraction of Genius lyric lines that received an LRC timestamp
    """
    genius_lines = _parse_genius_lines(genius_text)
    lrc_lines = parse_lrc_to_lines(lrc_synced)

    genius_lyrics = [line for line in genius_lines if line["kind"] == "lyric"]
    if not genius_lyrics or not lrc_lines:
        return {"lines": genius_lines, "match_rate": 0.0}

    genius_tokens = [_normalize_line(line["text"]) for line in genius_lyrics]
    lrc_tokens = [_normalize_line(line["text"]) for line in lrc_lines]

    genius_to_lrc = {}
    matched_count = 0
    matcher = SequenceMatcher(None, lrc_tokens, genius_tokens, autojunk=False)

    for tag, lrc_start, lrc_end, genius_start, genius_end in matcher.get_opcodes():
        if tag == "equal":
            for offset, genius_index in enumerate(range(genius_start, genius_end)):
                lrc_index = min(lrc_start + offset, len(lrc_lines) - 1)
                genius_to_lrc[genius_index] = lrc_lines[lrc_index]
                matched_count += 1
        elif tag == "replace":
            lrc_chunk = lrc_lines[lrc_start:lrc_end]
            genius_chunk_size = genius_end - genius_start
            if lrc_chunk and genius_chunk_size > 0:
                for genius_index in range(genius_start, genius_end):
                    lrc_index = lrc_start + min(
                        genius_index - genius_start,
                        len(lrc_chunk) - 1,
                    )
                    genius_to_lrc[genius_index] = lrc_chunk[lrc_index - lrc_start]
                    matched_count += 1

    for genius_index, line in enumerate(genius_lyrics):
        lrc_line = genius_to_lrc.get(genius_index)
        if lrc_line:
            line["start"] = lrc_line["start"]
            line["end"] = lrc_line["end"]

    match_rate = matched_count / max(len(genius_lyrics), 1)
    log.info(
        "merge_genius_lrclib: %d/%d genius lyric lines matched to LRC (%.0f%%)",
        matched_count, len(genius_lyrics), match_rate * 100,
    )

    return {"lines": genius_lines, "match_rate": match_rate}
