import os

from db.database import get_setting


def provider_result(lyrics=None, error=None, detail=None):
    return {
        "lyrics": lyrics,
        "source": "musixmatch" if lyrics else None,
        "error": error,
        "detail": detail,
    }


def fetch_lyrics_result(title, artist):
    api_key = (get_setting("musixmatch_key") or os.environ.get("MUSIXMATCH_API_KEY") or "").strip()
    if not api_key:
        return provider_result(error="No Musixmatch key is saved.")
    if not title:
        return provider_result(error="This track has no title to search.")

    try:
        from pymusixmatch import Musixmatch
    except ImportError as exc:
        return provider_result(error="Musixmatch lyrics dependency is not installed.", detail=str(exc))

    try:
        client = Musixmatch(api_key)
        response = client.matcher_lyrics_get(
            q_track=title,
            q_artist=artist or "",
        )
        body = response.get("message", {}).get("body", {})
        lyrics = body.get("lyrics", {}).get("lyrics_body")
        if not lyrics:
            return provider_result(error="Musixmatch did not return lyrics for this track.")
        lyrics = lyrics.split("******* This Lyrics is NOT for Commercial use *******")[0]
        cleaned = lyrics.strip()
        return provider_result(lyrics=cleaned) if cleaned else provider_result(error="Musixmatch lyrics were empty.")
    except Exception as exc:
        return provider_result(error="Musixmatch lyrics fetch failed.", detail=str(exc))


def fetch_lyrics(title, artist):
    return fetch_lyrics_result(title, artist).get("lyrics")
