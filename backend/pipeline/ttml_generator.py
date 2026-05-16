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
    """Ensure all slots are strictly monotonic and have a perceptible minimum duration.

    0.08s = 80ms minimum — a rAF tick at 60fps is ~16ms, so 10ms words are
    invisible (currentTime jumps over them). 80ms ensures at least 4-5 frames
    of highlight per word, which is the minimum the eye can perceive.
    """
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


def _clamp_slot_to_window(slot, window_start, window_end, min_duration=0.08):
    window_start = float(window_start)
    window_end = float(window_end)
    start = max(window_start, min(float(slot.get("start", window_start)), window_end - min_duration))
    end = max(start + min_duration, min(float(slot.get("end", start + min_duration)), window_end))
    return {"start": round(start, 3), "end": round(end, 3)}


def _anchored_slots_in_window(timed_words, lyric_words, window_start, window_end):
    """
    Match transcript words to lyric words within a time window, interpolate gaps,
    and clamp every slot to [window_start, window_end].
    """
    if not lyric_words:
        return []

    window_start = float(window_start)
    window_end = float(window_end)

    if not timed_words:
        return distribute_slots(window_start, window_end, len(lyric_words))

    transcript_pairs = [
        (index, normalized_token(word.get("word")))
        for index, word in enumerate(timed_words)
    ]
    transcript_pairs = [(index, token) for index, token in transcript_pairs if token]
    transcript_tokens = [token for _index, token in transcript_pairs]
    lyric_tokens = [normalized_token(word) for word in lyric_words]

    if not transcript_tokens:
        return distribute_slots(window_start, window_end, len(lyric_words))

    anchors = [None] * len(lyric_words)
    matcher = SequenceMatcher(None, transcript_tokens, lyric_tokens, autojunk=False)
    matched_count = 0

    for tag, transcript_start, transcript_end, lyric_start, lyric_end in matcher.get_opcodes():
        if tag == "equal":
            for offset, lyric_index in enumerate(range(lyric_start, lyric_end)):
                pair_index = min(transcript_start + offset, len(transcript_pairs) - 1)
                transcript_index = transcript_pairs[pair_index][0]
                timed_word = timed_words[transcript_index]
                anchors[lyric_index] = {
                    "start": float(timed_word.get("start", 0)),
                    "end": float(timed_word.get("end", timed_word.get("start", 0) + 0.12)),
                }
                matched_count += 1
        elif tag == "replace":
            target_count = lyric_end - lyric_start
            t_chunk = [
                timed_words[transcript_pairs[i][0]]
                for i in range(transcript_start, transcript_end)
                if i < len(transcript_pairs)
            ]
            if t_chunk:
                resampled = resampled_time_slots(t_chunk, target_count)
                if resampled and len(resampled) == target_count:
                    for offset, slot in enumerate(resampled):
                        anchors[lyric_start + offset] = slot
                    matched_count += target_count

    slots = [None] * len(lyric_words)
    anchor_indexes = [index for index, anchor in enumerate(anchors) if anchor]

    if not anchor_indexes:
        slots = distribute_slots(window_start, window_end, len(lyric_words))
        return [_clamp_slot_to_window(slot, window_start, window_end) for slot in slots]

    for index in anchor_indexes:
        slots[index] = anchors[index]

    first_anchor = anchor_indexes[0]
    for index, slot in enumerate(distribute_slots(window_start, slots[first_anchor]["start"], first_anchor)):
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
    for offset, slot in enumerate(distribute_slots(slots[last_anchor]["end"], window_end, tail_count), start=1):
        slots[last_anchor + offset] = slot

    clamped = [_clamp_slot_to_window(slot, window_start, window_end) for slot in slots]
    return enforce_monotonic_slots(clamped)


def lrc_constrained_time_slots(lrc_lines, whisperx_words, lyric_words):
    """
    Hybrid alignment: use LRC line timestamps as hard boundaries,
    WhisperX word timestamps within each line for word-level sync.
    """
    if not lrc_lines or not lyric_words:
        return []

    timed_words = [
        word for word in whisperx_words
        if word.get("start") is not None and word.get("end") is not None
    ]

    all_slots = []
    for line in lrc_lines:
        line_start = float(line["start"])
        line_end = float(line["end"])
        line_lyric_words = line.get("lyric_words") or []
        if not line_lyric_words:
            continue

        window_words = [
            word for word in timed_words
            if line_start <= float(word["start"]) <= line_end
        ]
        line_slots = _anchored_slots_in_window(
            window_words, line_lyric_words, line_start, line_end,
        )
        all_slots.extend(line_slots)

    expected = len(lyric_words)
    if len(all_slots) < expected:
        last_end = all_slots[-1]["end"] if all_slots else 0.0
        all_slots.extend(
            distribute_slots(last_end, last_end + (expected - len(all_slots)) * 0.2, expected - len(all_slots))
        )
    all_slots = all_slots[:expected]

    all_slots = enforce_monotonic_slots(all_slots)

    cursor = 0
    for line in lrc_lines:
        line_words = line.get("lyric_words") or []
        window_start = float(line["start"])
        window_end = float(line["end"])
        for index in range(cursor, cursor + len(line_words)):
            all_slots[index] = _clamp_slot_to_window(all_slots[index], window_start, window_end)
        cursor += len(line_words)

    return all_slots


def anchored_time_slots(timed_words, lyric_words):
    """
    Match transcript words to lyric words and interpolate only the gaps.
    This keeps copied lyric lines intact without blindly stretching the entire
    lyric sheet over every Whisper word when the transcription differs.
    """
    if not timed_words or not lyric_words:
        return [], 0

    transcript_pairs = [
        (index, normalized_token(word.get("word")))
        for index, word in enumerate(timed_words)
    ]
    transcript_pairs = [(index, token) for index, token in transcript_pairs if token]
    transcript_tokens = [token for _index, token in transcript_pairs]
    lyric_tokens = [normalized_token(word) for word in lyric_words]

    if not transcript_tokens:
        return [], 0

    anchors = [None] * len(lyric_words)
    matcher = SequenceMatcher(None, transcript_tokens, lyric_tokens, autojunk=False)
    matched_count = 0

    for tag, transcript_start, transcript_end, lyric_start, lyric_end in matcher.get_opcodes():
        if tag == "equal":
            for offset, lyric_index in enumerate(range(lyric_start, lyric_end)):
                pair_index = min(transcript_start + offset, len(transcript_pairs) - 1)
                transcript_index = transcript_pairs[pair_index][0]
                timed_word = timed_words[transcript_index]
                anchors[lyric_index] = {
                    "start": float(timed_word.get("start", 0)),
                    "end": float(timed_word.get("end", timed_word.get("start", 0) + 0.12)),
                }
                matched_count += 1
        elif tag == "replace":
            target_count = lyric_end - lyric_start
            t_chunk = [
                timed_words[transcript_pairs[i][0]]
                for i in range(transcript_start, transcript_end)
                if i < len(transcript_pairs)
            ]
            if t_chunk:
                resampled = resampled_time_slots(t_chunk, target_count)
                if resampled and len(resampled) == target_count:
                    for offset, slot in enumerate(resampled):
                        anchors[lyric_start + offset] = slot
                    matched_count += target_count

    minimum_matches = min(6, max(2, len(lyric_words) // 8))
    if matched_count < minimum_matches:
        return [], 0

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

    return enforce_monotonic_slots(slots), matched_count


def segment_guided_time_slots(transcript_segments, lyric_words):
    """
    Distribute lyric words across the transcript segment time-zones.
    Used as a fallback when anchored_time_slots has too few anchor matches
    (common in R&B / slow tracks with soft vocals).
    """
    if not transcript_segments or not lyric_words:
        return []

    # Only keep segments that contain real text (not synthetic tail segments)
    real_segments = [s for s in transcript_segments if str(s.get("text", "")).strip()]
    if not real_segments:
        real_segments = transcript_segments

    total_words = len(lyric_words)
    total_seg_duration = sum(
        max(float(s.get("end", 0)) - float(s.get("start", 0)), 0.01)
        for s in real_segments
    )

    slots = []
    cursor = 0
    for seg in real_segments:
        seg_start = float(seg.get("start", 0))
        seg_end = float(seg.get("end", seg_start + 0.1))
        seg_dur = max(seg_end - seg_start, 0.01)
        # Proportional word allocation
        word_count = max(1, round(total_words * seg_dur / total_seg_duration))
        word_count = min(word_count, total_words - cursor)
        if cursor + word_count >= total_words:
            word_count = total_words - cursor
        if word_count <= 0:
            break
        slots.extend(distribute_slots(seg_start, seg_end, word_count))
        cursor += word_count

    # Safety: pad/trim to exact word count
    if len(slots) < total_words:
        last_end = slots[-1]["end"] if slots else 0
        slots.extend(distribute_slots(last_end, last_end + (total_words - len(slots)) * 0.2, total_words - len(slots)))
    slots = slots[:total_words]
    return enforce_monotonic_slots(slots)


def words_with_lyrics_text(words, lyrics_text=None, transcript_segments=None, is_indic=False, lrc_lines=None):
    import logging
    log = logging.getLogger("ttml_generator")

    if lrc_lines:
        lyric_words = [word for line in lrc_lines for word in line.get("lyric_words", [])]
        records = None
    else:
        records = lyric_line_records(lyrics_text)
        lyric_lines = [record["words"] for record in records if record["kind"] == "lyric"]
        lyric_words = [word for line in lyric_lines for word in line]

    if not lyric_words:
        return words, None

    timed_words = [
        word for word in words
        if word.get("start") is not None and word.get("end") is not None
    ]

    log.info(
        "words_with_lyrics_text: %d WhisperX words, %d lyric words, %d transcript segments",
        len(timed_words), len(lyric_words), len(transcript_segments or []),
    )

    if lrc_lines:
        log.info(
            "Using hybrid LRC-constrained alignment: %d lrc_lines, %d whisperx_words",
            len(lrc_lines), len(timed_words),
        )
        slots = lrc_constrained_time_slots(lrc_lines, timed_words, lyric_words)
        used_fallback = False
        matched_count = len(lyric_words)
        match_rate = 1.0
    else:
        slots, matched_count = anchored_time_slots(timed_words, lyric_words)
        used_fallback = False
        match_rate = matched_count / max(len(lyric_words), 1)

    if not lrc_lines and slots:
        durations = [round(s["end"] - s["start"], 2) for s in slots]
        dur_counts = Counter(durations)
        most_common_count = dur_counts.most_common(1)[0][1] if dur_counts else 0
        flat_pct = most_common_count / len(slots) if slots else 0

        truly_flat = flat_pct > 0.50 and match_rate < 0.25
        if truly_flat:
            log.warning(
                "anchored_time_slots: match_rate=%.0f%% flat_pct=%.0f%% — "
                "insufficient anchors + flat interpolation. Falling back to segment-guided.",
                match_rate * 100, flat_pct * 100,
            )
            slots = []
            used_fallback = True
        else:
            log.info(
                "anchored_time_slots: %d/%d words matched (%.0f%%), flat_pct=%.1f%% — "
                "using anchored timestamps.",
                matched_count, len(lyric_words), match_rate * 100, flat_pct * 100,
            )

    # 6d: Indian language tracks with poor CTC alignment (<40% match) —
    # fall back to line-level sync by distributing words evenly within each
    # lyric line's segment boundary. Much better UX than random word flashes.
    if not lrc_lines and is_indic and match_rate < 0.40 and transcript_segments:
        log.info(
            "Indian language track with low match rate (%.0f%%) — using line-level sync.",
            match_rate * 100,
        )
        slots = _line_level_slots(records, transcript_segments, lyric_words)
        used_fallback = True

    if not lrc_lines and not slots:
        if transcript_segments:
            log.info("Using segment_guided_time_slots with %d segments.", len(transcript_segments))
            slots = segment_guided_time_slots(transcript_segments, lyric_words)
        else:
            log.warning("No transcript segments available — falling back to uniform distribution.")
            total_start = timed_words[0].get("start", 0) if timed_words else 0
            total_end = timed_words[-1].get("end", total_start + len(lyric_words) * 0.2) if timed_words else total_start + len(lyric_words) * 0.2
            slots = distribute_slots(total_start, total_end, len(lyric_words))
            slots = enforce_monotonic_slots(slots)

    # Log first 5 slots for inspection
    for i, slot in enumerate(slots[:5]):
        if lrc_lines:
            source = "hybrid"
        else:
            source = "segment-guided" if used_fallback else "anchored"
        log.info("  slot[%d] %s  start=%.3f  end=%.3f  word=%s",
                 i, source, slot["start"], slot["end"],
                 lyric_words[i] if i < len(lyric_words) else "?")

    # Build mapped_words
    mapped_words = []
    for i, lyric_word in enumerate(lyric_words):
        slot = slots[i] if i < len(slots) else {"start": 0, "end": 0}
        mapped_words.append({
            "word": lyric_word,
            "start": slot["start"],
            "end": slot["end"],
        })

    # Build groups matching original lyric structure
    groups = []
    cursor = 0
    if lrc_lines:
        for line in lrc_lines:
            count = len(line.get("lyric_words", []))
            groups.append({
                "kind": "lyric",
                "text": line["text"],
                "words": mapped_words[cursor:cursor + count],
            })
            cursor += count
    else:
        for record in records:
            if record["kind"] != "lyric":
                groups.append({**record, "words": []})
                continue
            count = len(record["words"])
            groups.append({**record, "words": mapped_words[cursor:cursor + count]})
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


def _line_level_slots(records, transcript_segments, lyric_words):
    """
    Line-level sync fallback for Indian language tracks (Task 6d).

    Distributes words evenly within each lyric line's time window.
    Line windows are derived from transcript_segments by proportionally
    splitting the total segment time across lyric lines by word count.
    """
    lyric_line_records_only = [r for r in records if r["kind"] == "lyric"]
    if not lyric_line_records_only or not transcript_segments:
        return []

    total_duration = sum(
        max(float(s.get("end", 0)) - float(s.get("start", 0)), 0.01)
        for s in transcript_segments
    ) or 1.0
    audio_start = float(transcript_segments[0].get("start", 0))
    audio_end = float(transcript_segments[-1].get("end", audio_start + total_duration))
    total_span = max(audio_end - audio_start, 1.0)

    total_lyric_words = len(lyric_words)
    slots = []
    cursor = 0.0
    accumulated = audio_start

    for line_record in lyric_line_records_only:
        line_word_count = len(line_record["words"])
        if line_word_count == 0:
            continue
        # Each line gets a share of the total span proportional to its word count
        line_share = line_word_count / max(total_lyric_words, 1)
        line_duration = total_span * line_share
        line_start = accumulated
        line_end = accumulated + line_duration
        slots.extend(distribute_slots(line_start, line_end, line_word_count))
        accumulated = line_end

    return enforce_monotonic_slots(slots)


def apply_lyrics_to_words(words, lyrics_text=None, transcript_segments=None, is_indic=False, lrc_lines=None):
    mapped_words, lyric_groups = words_with_lyrics_text(
        words, lyrics_text, transcript_segments=transcript_segments, is_indic=is_indic, lrc_lines=lrc_lines,
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
                  transcript_segments=None, is_indic=False, lrc_lines=None):
    language = language or "en"
    original_words = words
    words, groups = apply_lyrics_to_words(
        words, lyrics_text, transcript_segments=transcript_segments, is_indic=is_indic, lrc_lines=lrc_lines,
    )
    if include_phonetics:
        words = apply_phonetics(words, original_words)
    sync_source_attr = ' data-sync-source="hybrid"' if lrc_lines else ""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<tt xml:lang="{escape(language)}" xmlns="http://www.w3.org/ns/ttml"'
        f' xmlns:tts="http://www.w3.org/ns/ttml#styling"{sync_source_attr}>',
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
