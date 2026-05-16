import sys
import unittest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from lyrics.lyrics_merger import merge_genius_lrclib
from lyrics.lrc_to_ttml import merged_lines_to_ttml


class LyricsMergerTests(unittest.TestCase):
    def test_merge_assigns_lrc_timestamps(self):
        genius = "\n".join([
            "[Chorus]",
            "Driftin' away like a feather",
            "Second line here",
        ])
        lrc = "\n".join([
            "[00:10.00] Driftin' away like a feather",
            "[00:15.00] Second line here",
        ])
        merged = merge_genius_lrclib(genius, lrc)
        self.assertGreaterEqual(merged["match_rate"], 0.5)
        lyric_lines = [line for line in merged["lines"] if line["kind"] == "lyric"]
        self.assertEqual(len(lyric_lines), 2)
        self.assertEqual(lyric_lines[0]["start"], 10.0)
        self.assertEqual(lyric_lines[1]["start"], 15.0)

    def test_merged_lines_to_ttml_has_sync_source(self):
        lines = [
            {"kind": "label", "text": "[Chorus]", "start": None, "end": None},
            {"kind": "lyric", "text": "Hello world", "start": 1.0, "end": 3.0},
        ]
        ttml = merged_lines_to_ttml(lines)
        self.assertIn('data-sync-source="genius+lrclib"', ttml)
        self.assertIn('data-kind="label"', ttml)
        self.assertIn('data-kind="lyric"', ttml)


if __name__ == "__main__":
    unittest.main()
