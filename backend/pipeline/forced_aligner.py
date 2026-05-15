import os
import logging
from typing import List, Dict

# Simple fallback forced aligner implementation.
# This module provides `align_lyrics` which returns a list of segment dicts
# with `start`, `end`, and `text` keys. If a more sophisticated aligner
# (e.g., Gentle, MFA) is installed, it can be used here. For now we fall
# back to a uniform distribution over the entire audio duration.

def _get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using librosa, or 0.0 on failure."""
    try:
        import librosa
        return float(librosa.get_duration(path=audio_path))
    except Exception as e:
        logging.getLogger(__name__).warning("Could not determine audio duration: %s", e)
        return 0.0


def align_lyrics(audio_path: str, lyrics_text: str, language: str = "en") -> List[Dict]:
    """Return forced‑alignment segments for the provided lyrics.

    The current implementation is a lightweight fallback that treats the
    entire lyrics as a single segment spanning the full audio duration.
    More advanced aligners can be integrated later.

    Parameters
    ----------
    audio_path: str
        Path to the audio file.
    lyrics_text: str
        Full lyrics text.
    language: str, optional
        Language code (unused in this simple implementation).
    """
    duration = _get_audio_duration(audio_path)
    if duration <= 0:
        # If we cannot determine duration, default to 0 and let the caller
        # handle interpolation.
        duration = 0.0
    # Return a single segment covering the whole audio.
    return [{"start": 0.0, "end": duration, "text": lyrics_text}]
