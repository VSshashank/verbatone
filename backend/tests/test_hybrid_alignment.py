import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from lyrics.lrc_to_ttml import parse_lrc_to_lines
from pipeline.ttml_generator import lrc_constrained_time_slots


class ParseLrcToLinesTests(unittest.TestCase):
    def test_end_and_words(self):
        lrc = "\n".join([
            "[00:43.15] Driftin' away like a feather in air",
            "[01:03.20] Driftin' away like a feather in air",
        ])
        lines = parse_lrc_to_lines(lrc)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["start"], 43.15)
        self.assertAlmostEqual(lines[0]["end"], 63.15, places=2)
        self.assertEqual(lines[0]["text"], "Driftin' away like a feather in air")
        self.assertEqual(
            lines[0]["lyric_words"],
            ["Driftin'", "away", "like", "a", "feather", "in", "air"],
        )
        self.assertEqual(lines[1]["start"], 63.2)
        self.assertAlmostEqual(lines[1]["end"], 68.2, places=2)

    def test_skips_instrumental(self):
        lrc = "\n".join([
            "[00:10.00] ♪",
            "[00:15.00] Hello world",
        ])
        lines = parse_lrc_to_lines(lrc)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["text"], "Hello world")


class LrcConstrainedTimeSlotsTests(unittest.TestCase):
    def test_chorus_windows(self):
        line_text = "Driftin' away like a feather in air"
        lyric_words = line_text.split()
        lrc_lines = [
            {
                "start": 43.15,
                "end": 45.10,
                "text": line_text,
                "lyric_words": lyric_words,
            },
            {
                "start": 63.20,
                "end": 65.10,
                "text": line_text,
                "lyric_words": lyric_words,
            },
        ]
        flat_lyric_words = lyric_words * 2

        whisperx_words = []
        for word, start, end in [
            ("Driftin'", 43.2, 43.5),
            ("away", 43.6, 43.9),
            ("like", 44.0, 44.2),
            ("a", 44.3, 44.4),
            ("feather", 44.5, 44.8),
            ("in", 44.9, 45.0),
            ("air", 45.0, 45.05),
            ("Driftin'", 63.3, 63.6),
            ("away", 63.7, 64.0),
            ("like", 64.1, 64.3),
            ("a", 64.4, 64.5),
            ("feather", 64.6, 64.9),
            ("in", 65.0, 65.05),
            ("air", 65.05, 65.08),
        ]:
            whisperx_words.append({"word": word, "start": start, "end": end})

        slots = lrc_constrained_time_slots(lrc_lines, whisperx_words, flat_lyric_words)

        self.assertEqual(len(slots), len(flat_lyric_words))

        chorus1 = slots[:7]
        chorus2 = slots[7:]

        for slot in chorus1:
            self.assertGreaterEqual(slot["start"], 43.15)
            self.assertLessEqual(slot["start"], 45.10)
            self.assertGreaterEqual(slot["end"], 43.15)
            self.assertLessEqual(slot["end"], 45.10)

        for slot in chorus2:
            self.assertGreaterEqual(slot["start"], 63.20)
            self.assertLessEqual(slot["start"], 65.10)
            self.assertGreaterEqual(slot["end"], 63.20)
            self.assertLessEqual(slot["end"], 65.10)

        self.assertLess(chorus1[-1]["end"], chorus2[0]["start"])

    def test_ignores_whisperx_outside_window(self):
        line_text = "Hello world"
        lrc_lines = [{
            "start": 10.0,
            "end": 12.0,
            "text": line_text,
            "lyric_words": ["Hello", "world"],
        }]
        whisperx_words = [
            {"word": "Hello", "start": 10.1, "end": 10.5},
            {"word": "world", "start": 10.6, "end": 11.0},
            {"word": "stray", "start": 62.0, "end": 62.5},
        ]
        slots = lrc_constrained_time_slots(lrc_lines, whisperx_words, ["Hello", "world"])

        self.assertEqual(len(slots), 2)
        for slot in slots:
            self.assertGreaterEqual(slot["start"], 10.0)
            self.assertLessEqual(slot["start"], 12.0)
            self.assertGreaterEqual(slot["end"], 10.0)
            self.assertLessEqual(slot["end"], 12.0)


if __name__ == "__main__":
    unittest.main()
