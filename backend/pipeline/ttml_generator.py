import re
from collections import Counter
from difflib import SequenceMatcher
from html import escape


def seconds_to_ttml_time(seconds):
    seconds = max(float(seconds or 0), 0)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{remainder:06.3f}"


def lyric_line_records(lyrics_text):
    records = []
    previous_gap = False

    for line in (lyrics_text or "").splitlines():
        cleaned = line.strip()
        if not cleaned:
            if records and not previous_gap:
                records.append({"kind": "gap", "text": "", "words": []})
                previous_gap = True
            continue

        lowered = cleaned.lower()
        if lowered.startswith(("embed", "you might also like")):
            continue

        cleaned = re.sub(r"\d*embed$", "", cleaned, flags=re.IGNORECASE).strip()
        if not cleaned:
            continue

        if re.fullmatch(r"\[.*?\]", cleaned):
            records.append({"kind": "label", "text": cleaned, "words": []})
        else:
            records.append({
                "kind": "lyric",
                "text": cleaned,
                "words": re.findall(r"\S+", cleaned),
            })
        previous_gap = False

    while records and records[0]["kind"] == "gap":
        records.pop(0)
    while records and records[-1]["kind"] == "gap":
        records.pop()

    return records


def line_texts(lyrics_text):
    return [
        record["text"]
        for record in lyric_line_records(lyrics_text)
        if record["kind"] == "lyric"
    ]


def lyric_word_lines(lyrics_text):
    return [
        record["words"]
        for record in lyric_line_records(lyrics_text)
        if record["kind"] == "lyric"
    ]


def group_words(words, lyrics_text=None, max_gap=1.25, max_words=10):
    lyric_lines = lyric_word_lines(lyrics_text)
    lines = [" ".join(line) for line in lyric_lines]
    groups = []
    current = []
    line_idx = 0
    target_count = len(lyric_lines[line_idx]) if lyric_lines else max_words

    for word in words:
        if not current:
            current.append(word)
            continue

        previous = current[-1]
        gap = float(word.get("start", 0)) - float(previous.get("end", 0))
        reached_line_length = lines and len(current) >= max(target_count, 1)
        reached_default_length = not lines and len(current) >= max_words

        if gap > max_gap or reached_line_length or reached_default_length:
            groups.append(current)
            current = [word]
            if lyric_lines:
                line_idx = min(line_idx + 1, len(lyric_lines) - 1)
                target_count = len(lyric_lines[line_idx])
        else:
            current.append(word)

    if current:
        groups.append(current)
    return groups


def resampled_time_slots(timed_words, target_count):
    if not timed_words or target_count <= 0:
        return []

    source_count = len(timed_words)
    total_start = float(timed_words[0].get("start", 0))
    total_end = float(timed_words[-1].get("end", total_start + 0.12))
    total_duration = max(total_end - total_start, target_count * 0.12)

    if target_count > source_count:
        return [
            {
                "start": round(total_start + (index / target_count) * total_duration, 3),
                "end": round(total_start + ((index + 1) / target_count) * total_duration, 3),
            }
            for index in range(target_count)
        ]

    slots = []
    for index in range(target_count):
        start_source = int(index * source_count / target_count)
        end_source = max(start_source, int((index + 1) * source_count / target_count) - 1)
        start_word = timed_words[min(start_source, source_count - 1)]
        end_word = timed_words[min(end_source, source_count - 1)]
        start = float(start_word.get("start", 0))
        end = float(end_word.get("end", start + 0.12))
        if end <= start:
            end = start + 0.12
        slots.append({"start": round(start, 3), "end": round(end, 3)})

    for index in range(1, len(slots)):
        if slots[index]["start"] < slots[index - 1]["end"]:
            midpoint = (slots[index]["start"] + slots[index - 1]["end"]) / 2
            slots[index - 1]["end"] = round(midpoint, 3)
            slots[index]["start"] = round(midpoint, 3)
        if slots[index]["end"] <= slots[index]["start"]:
            slots[index]["end"] = round(slots[index]["start"] + 0.12, 3)

    return slots


def normalized_token(value):
    return re.sub(r"[^\w']+", "", str(value or "").lower(), flags=re.UNICODE).strip("_'")


def enforce_monotonic_slots(slots, min_duration=0.08):
    cleaned = []
    cursor = 0.0
    for slot in slots:
        start = max(float(slot.get("start", cursor)), cursor)
        end = max(float(slot.get("end", start + min_duration)), start + min_duration)
        cleaned.append({"start": round(start, 3), "end": round(end, 3)})
        cursor = end
    return cleaned


def distribute_slots(start, end, count, min_duration=0.08):
    if count <= 0:
        return []

    start = float(start)
    end = max(float(end), start + count * min_duration)
    duration = end - start
    return [
        {
            "start": round(start + (index / count) * duration, 3),
            "end": round(start + ((index + 1) / count) * duration, 3),
        }
        for index in range(count)
    ]


def anchored_time_slots(timed_words, lyric_words):
    """
    Match transcript words to lyric words and interpolate only the gaps.
    This keeps copied lyric lines intact without blindly stretching the entire
    lyric sheet over every Whisper word when the transcription differs.
    """
    if not timed_words or not lyric_words:
        return []

    transcript_pairs = [
        (index, normalized_token(word.get("word")))
        for index, word in enumerate(timed_words)
    ]
    transcript_pairs = [(index, token) for index, token in transcript_pairs if token]
    transcript_tokens = [token for _index, token in transcript_pairs]
    lyric_tokens = [normalized_token(word) for word in lyric_words]

    if not transcript_tokens:
        return []

    anchors = [None] * len(lyric_words)
    matcher = SequenceMatcher(None, transcript_tokens, lyric_tokens, autojunk=False)
    matched_count = 0

    for tag, transcript_start, _transcript_end, lyric_start, lyric_end in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset, lyric_index in enumerate(range(lyric_start, lyric_end)):
            pair_index = min(transcript_start + offset, len(transcript_pairs) - 1)
            transcript_index = transcript_pairs[pair_index][0]
            timed_word = timed_words[transcript_index]
            anchors[lyric_index] = {
                "start": float(timed_word.get("start", 0)),
                "end": float(timed_word.get("end", timed_word.get("start", 0) + 0.12)),
            }
            matched_count += 1

    minimum_matches = min(6, max(2, len(lyric_words) // 8))
    if matched_count < minimum_matches:
        return []

    total_start = float(timed_words[0].get("start", 0))
    total_end = float(timed_words[-1].get("end", total_start + len(lyric_words) * 0.16))
    slots = [None] * len(lyric_words)
    anchor_indexes = [index for index, anchor in enumerate(anchors) if anchor]

    for index in anchor_indexes:
        slots[index] = anchors[index]

    first_anchor = anchor_indexes[0]
    for index, slot in enumerate(distribute_slots(total_start, slots[first_anchor]["start"], first_anchor)):
        slots[index] = slot

    for left, right in zip(anchor_indexes, anchor_indexes[1:]):
        gap_count = right - left - 1
        if gap_count <= 0:
            continue
        gap_slots = distribute_slots(slots[left]["end"], slots[right]["start"], gap_count)
        for offset, slot in enumerate(gap_slots, start=1):
            slots[left + offset] = slot

    last_anchor = anchor_indexes[-1]
    tail_count = len(lyric_words) - last_anchor - 1
    for offset, slot in enumerate(distribute_slots(slots[last_anchor]["end"], total_end, tail_count), start=1):
        slots[last_anchor + offset] = slot

    return enforce_monotonic_slots(slots)


def segment_guided_time_slots(transcript_segments, lyric_words):
    """
    Distribute lyric words across WhisperX transcript segment boundaries.

    When anchored_time_slots fails (too few word-level matches), this function
    uses the raw transcript segments as timing guardrails.  Each segment's text
    is fuzzy-matched against the remaining lyrics to decide how many lyric words
    belong in each time zone.  Words within a zone are evenly distributed.

    This is the key fix for R&B and slow-tempo tracks where WhisperX only
    detects a few segments but the lyrics have many more words.
    """
    if not transcript_segments or not lyric_words:
        return []

    # Tokenise each segment's transcript text
    seg_data = []
    for seg in transcript_segments:
        seg_tokens = [normalized_token(w) for w in re.findall(r"\S+", seg.get("text", ""))]
        seg_tokens = [t for t in seg_tokens if t]
        if not seg_tokens:
            continue
        seg_data.append({
            "start": float(seg.get("start", 0)),
            "end": float(seg.get("end", 0)),
            "tokens": seg_tokens,
        })

    if not seg_data:
        return []

    lyric_tokens = [normalized_token(w) for w in lyric_words]

    # Greedily assign lyric words to segments by fuzzy-matching each segment's
    # transcript tokens against the remaining lyric tokens.
    assignments = []  # list of (seg_start, seg_end, lyric_slice_start, lyric_slice_end)
    lyric_cursor = 0

    for seg in seg_data:
        if lyric_cursor >= len(lyric_tokens):
            break

        remaining_lyrics = lyric_tokens[lyric_cursor:]
        seg_tok = seg["tokens"]

        # Use SequenceMatcher to find the best alignment window.
        # We try matching the segment's tokens against successive windows
        # of the remaining lyrics and pick the one with the best match ratio.
        best_end = lyric_cursor + len(seg_tok)  # default: proportional
        best_ratio = 0.0

        # Search window: allow up to 2x the segment token count
        search_limit = min(len(remaining_lyrics), len(seg_tok) * 3)
        for candidate_end in range(max(1, len(seg_tok) // 2), search_limit + 1):
            candidate = remaining_lyrics[:candidate_end]
            matcher = SequenceMatcher(None, seg_tok, candidate, autojunk=False)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_end = lyric_cursor + candidate_end

        # If match is terrible, fall back to proportional word count
        if best_ratio < 0.15:
            total_seg_words = sum(len(s["tokens"]) for s in seg_data)
            proportion = len(seg_tok) / max(total_seg_words, 1)
            best_end = lyric_cursor + max(1, round(proportion * len(lyric_words)))

        best_end = min(best_end, len(lyric_words))
        if best_end <= lyric_cursor:
            best_end = min(lyric_cursor + 1, len(lyric_words))

        assignments.append((seg["start"], seg["end"], lyric_cursor, best_end))
        lyric_cursor = best_end

    # Any remaining lyrics get appended to the last segment
    if lyric_cursor < len(lyric_words) and assignments:
        last_start, last_end, last_l_start, _last_l_end = assignments[-1]
        assignments[-1] = (last_start, last_end, last_l_start, len(lyric_words))
    elif lyric_cursor < len(lyric_words) and not assignments:
        # Shouldn't happen, but handle gracefully
        return []

    # Distribute words within each segment evenly
    slots = [None] * len(lyric_words)
    for seg_start, seg_end, l_start, l_end in assignments:
        count = l_end - l_start
        if count <= 0:
            continue
        chunk = distribute_slots(seg_start, seg_end, count)
        for offset, slot in enumerate(chunk):
            slots[l_start + offset] = slot

    # Fill any remaining None slots
    for i in range(len(slots)):
        if slots[i] is None:
            prev_end = slots[i - 1]["end"] if i > 0 and slots[i - 1] else 0.0
            slots[i] = {"start": prev_end, "end": prev_end + 0.2}

    return enforce_monotonic_slots(slots)


def words_with_lyrics_text(words, lyrics_text=None, transcript_segments=None):
    records = lyric_line_records(lyrics_text)
    lyric_lines = [record["words"] for record in records if record["kind"] == "lyric"]
    lyric_words = [word for line in lyric_lines for word in line]
    if not lyric_words:
        return words, None

    timed_words = [
        word for word in words
        if word.get("start") is not None and word.get("end") is not None
    ]
    if not timed_words:
        return words, None

    slots = anchored_time_slots(timed_words, lyric_words)

    # Quality check: detect when anchored_time_slots produced sparse results.
    # When anchors are sparse, distribute_slots fills gaps with uniform-duration
    # words (e.g. all exactly 1.62s).  If >15% of words share the same duration
    # (rounded to 2 decimals), the result is too flat and we should prefer
    # segment-guided distribution.
    use_segment_guided = not slots
    if slots and transcript_segments and len(slots) > 10:
        durations = [round(s["end"] - s["start"], 2) for s in slots]
        duration_counts = Counter(durations)
        most_common_count = duration_counts.most_common(1)[0][1]
        if most_common_count > len(slots) * 0.15:
            use_segment_guided = True

    if use_segment_guided and transcript_segments:
        guided = segment_guided_time_slots(transcript_segments, lyric_words)
        if guided:
            slots = guided

    if not slots:
        return words, None

    mapped_words = [
        {
            **slots[index],
            "word": lyric_words[index],
            "phonetic": None,
        }
        for index in range(len(lyric_words))
    ]

    groups = []
    cursor = 0
    for record in records:
        if record["kind"] != "lyric":
            groups.append({**record, "words": []})
            continue
        count = len(record["words"])
        if count:
            groups.append({
                **record,
                "words": mapped_words[cursor:cursor + count],
            })
            cursor += count

    return mapped_words, groups


def timing_groups(words, max_gap=1.25, max_words=10):
    groups = []
    current = []
    for word in words:
        if not current:
            current.append(word)
            continue
        previous = current[-1]
        gap = float(word.get("start", 0)) - float(previous.get("end", 0))
        if gap > max_gap or len(current) >= max_words:
            groups.append({
                "kind": "lyric",
                "text": " ".join(str(item.get("word", "")).strip() for item in current).strip(),
                "words": current,
            })
            current = [word]
        else:
            current.append(word)
    if current:
        groups.append({
            "kind": "lyric",
            "text": " ".join(str(item.get("word", "")).strip() for item in current).strip(),
            "words": current,
        })
    return groups


def apply_lyrics_to_words(words, lyrics_text=None, transcript_segments=None):
    mapped_words, lyric_groups = words_with_lyrics_text(
        words, lyrics_text, transcript_segments=transcript_segments,
    )
    if lyric_groups:
        return mapped_words, lyric_groups
    return mapped_words, timing_groups(mapped_words)


def apply_phonetics(words, original_words):
    if len(words) != len(original_words):
        return words
    return [
        {
            **word,
            "phonetic": original_words[index].get("phonetic"),
        }
        for index, word in enumerate(words)
    ]


def generate_ttml(words, lyrics_text=None, language="en", include_phonetics=False,
                  transcript_segments=None):
    language = language or "en"
    original_words = words
    words, groups = apply_lyrics_to_words(
        words, lyrics_text, transcript_segments=transcript_segments,
    )
    if include_phonetics:
        words = apply_phonetics(words, original_words)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<tt xml:lang="{escape(language)}" xmlns="http://www.w3.org/ns/ttml"'
        ' xmlns:tts="http://www.w3.org/ns/ttml#styling">',
        "  <head>",
        "    <styling>",
        '      <style xml:id="default" tts:color="white" tts:fontSize="120%"/>',
        '      <style xml:id="active"  tts:color="yellow" tts:fontWeight="bold"/>',
        '      <style xml:id="phonetic" tts:color="#a0a0a0" tts:fontSize="75%"/>',
        "    </styling>",
        "  </head>",
        "  <body>",
        "    <div>",
    ]

    for group_record in groups:
        if isinstance(group_record, dict):
            kind = group_record.get("kind", "lyric")
            display_text = escape(str(group_record.get("text", "")).strip(), quote=True)
            group = group_record.get("words", [])
        else:
            kind = "lyric"
            group = group_record
            display_text = escape(
                " ".join(str(word.get("word", "")).strip() for word in group).strip(),
                quote=True,
            )

        if kind != "lyric":
            lines.append(f'      <p data-kind="{escape(kind, quote=True)}" data-text="{display_text}"/>')
            continue

        group = [word for word in group if word.get("start") is not None and word.get("end") is not None]
        if not group:
            continue
        begin = seconds_to_ttml_time(group[0].get("start", 0))
        end   = seconds_to_ttml_time(group[-1].get("end", group[-1].get("start", 0)))
        lines.append(f'      <p begin="{begin}" end="{end}" data-kind="lyric" data-text="{display_text}">')
        for word in group:
            word_begin = seconds_to_ttml_time(word.get("start", 0))
            word_end   = seconds_to_ttml_time(word.get("end", word.get("start", 0)))
            text     = escape(str(word.get("word", "")).strip())
            phonetic = escape(str(word.get("phonetic", "")).strip())
            if not text:
                continue
            if include_phonetics and phonetic and phonetic != text:
                lines.append(
                    f'        <span begin="{word_begin}" end="{word_end}">'
                    f'<span style="default">{text} </span>'
                    f'<span style="phonetic">{phonetic} </span>'
                    f'</span>'
                )
            else:
                lines.append(
                    f'        <span begin="{word_begin}" end="{word_end}">{text} </span>'
                )
        lines.append("      </p>")

    lines.extend(["    </div>", "  </body>", "</tt>"])
    return "\n".join(lines)
