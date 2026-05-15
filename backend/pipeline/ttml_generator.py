import re
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


def words_with_lyrics_text(words, lyrics_text=None):
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

    if len(lyric_words) == len(timed_words):
        mapped_words = [
            {
                **word,
                "word": lyric_words[index],
            }
            for index, word in enumerate(timed_words)
        ]
    else:
        slots = resampled_time_slots(timed_words, len(lyric_words))
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


def apply_lyrics_to_words(words, lyrics_text=None):
    mapped_words, lyric_groups = words_with_lyrics_text(words, lyrics_text)
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


def generate_ttml(words, lyrics_text=None, language="en", include_phonetics=False):
    language = language or "en"
    original_words = words
    words, groups = apply_lyrics_to_words(words, lyrics_text)
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
