#!/usr/bin/env python3
"""Usage: python3 scripts/test_stable_ts.py path/to/audio.mp3 "lyrics text here"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pipeline.stable_ts_runner import align


def main():
    if len(sys.argv) < 3:
        print('Usage: python3 scripts/test_stable_ts.py path/to/audio.mp3 "lyrics text here"')
        sys.exit(1)

    audio_path = sys.argv[1]
    lyrics_text = sys.argv[2]
    result = align(audio_path, lyrics_text)
    words = result["words"]
    print(f"Total words: {len(words)}")
    print(f"Language: {result.get('language')}")
    for word in words[:20]:
        print(f"  {word['start']:.3f} → {word['end']:.3f}  {word['word']}")


if __name__ == "__main__":
    main()
