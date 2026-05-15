#!/usr/bin/env python3
"""
Usage: python scripts/inspect_ttml.py <ttml_file>

Diagnoses a TTML file for alignment quality:
- Word counts and duration statistics
- Detection of interpolated/unaligned words
- Gap analysis between consecutive words
- First and last 20 word timestamps
"""
import sys
import statistics
import xml.etree.ElementTree as ET


def time_to_seconds(value):
    if not value:
        return 0.0
    parts = value.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return float(value)


def inspect(path):
    tree = ET.parse(path)
    root = tree.getroot()

    ns = {"tt": "http://www.w3.org/ns/ttml"}

    words = []
    for span in root.iter("{http://www.w3.org/ns/ttml}span"):
        begin = span.get("begin")
        end = span.get("end")
        text = (span.text or "").strip()
        if begin and end and text:
            start_s = time_to_seconds(begin)
            end_s = time_to_seconds(end)
            words.append({"text": text, "start": start_s, "end": end_s, "duration": end_s - start_s})

    if not words:
        print("ERROR: No timed word spans found in the TTML.")
        return

    durations = [w["duration"] for w in words]
    total = len(words)

    # Stats
    mean_dur = statistics.mean(durations)
    median_dur = statistics.median(durations)
    min_dur = min(durations)
    max_dur = max(durations)

    short_count = sum(1 for d in durations if d < 0.05)
    long_count = sum(1 for d in durations if d > 2.0)

    # Identical duration runs (interpolation fingerprint)
    rounded = [round(d, 3) for d in durations]
    from collections import Counter
    dur_counts = Counter(rounded)
    most_common_dur, most_common_count = dur_counts.most_common(1)[0]
    pct_most_common = most_common_count / total * 100

    # Gaps between consecutive words
    big_gaps = []
    for i in range(1, len(words)):
        gap = words[i]["start"] - words[i - 1]["end"]
        if gap > 3.0:
            big_gaps.append({
                "between": f"{words[i-1]['text']} -> {words[i]['text']}",
                "gap_s": round(gap, 3),
                "at": round(words[i - 1]["end"], 3),
            })

    print("=" * 60)
    print(f"TTML FILE: {path}")
    print("=" * 60)
    print(f"\n  Total words      : {total}")
    print(f"  Duration stats   : min={min_dur:.3f}s  max={max_dur:.3f}s  mean={mean_dur:.3f}s  median={median_dur:.3f}s")
    print(f"  Short (<0.05s)   : {short_count} ({100*short_count/total:.1f}%)  — likely unaligned/collapsed")
    print(f"  Long (>2s)       : {long_count}  ({100*long_count/total:.1f}%)  — likely flat-interpolated")
    print(f"  Most-common dur  : {most_common_dur:.3f}s appears {most_common_count}x ({pct_most_common:.1f}% of all words)  ← interpolation fingerprint if >15%")
    print(f"\n  Gaps > 3s between consecutive words: {len(big_gaps)}")
    for g in big_gaps:
        print(f"    @ {g['at']:.1f}s  gap={g['gap_s']:.1f}s  [{g['between']}]")

    print(f"\n  FIRST 20 WORDS:")
    print(f"  {'#':>4}  {'text':<20}  {'start':>8}  {'end':>8}  {'dur':>7}")
    print("  " + "-" * 55)
    for i, w in enumerate(words[:20]):
        print(f"  {i+1:>4}  {w['text']:<20}  {w['start']:>8.3f}  {w['end']:>8.3f}  {w['duration']:>7.3f}")

    print(f"\n  LAST 20 WORDS:")
    print(f"  {'#':>4}  {'text':<20}  {'start':>8}  {'end':>8}  {'dur':>7}")
    print("  " + "-" * 55)
    for i, w in enumerate(words[-20:], start=max(1, total - 19)):
        print(f"  {i:>4}  {w['text']:<20}  {w['start']:>8.3f}  {w['end']:>8.3f}  {w['duration']:>7.3f}")

    print()

    # Verdict
    print("  DIAGNOSIS:")
    if pct_most_common > 15:
        print(f"  ⚠️  INTERPOLATION DETECTED: {pct_most_common:.1f}% of words share the same duration ({most_common_dur:.3f}s).")
        print("      WhisperX alignment likely failed — most timestamps are mathematically distributed,")
        print("      NOT from actual phoneme detection. This is the primary cause of drift.")
    elif long_count / total > 0.25:
        print("  ⚠️  HIGH % of long words (>2s). Segment-guided distribution produced wide, imprecise slots.")
    elif short_count / total > 0.10:
        print("  ⚠️  HIGH % of sub-50ms words. CTC alignment collapsed many words to near-zero duration.")
    else:
        print("  ✅  Duration distribution looks healthy. Drift may be a frontend clock or parse issue.")

    song_span = words[-1]["end"] - words[0]["start"]
    print(f"\n  Lyrics span: {words[0]['start']:.1f}s → {words[-1]['end']:.1f}s  (total {song_span:.1f}s)")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <ttml_file>")
        sys.exit(1)
    inspect(sys.argv[1])
