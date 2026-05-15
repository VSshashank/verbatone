import os

from db.database import get_setting


def fetch_lyrics(title, artist):
    api_key = get_setting("musixmatch_key") or os.environ.get("MUSIXMATCH_API_KEY")
    if not api_key or not title:
        return None

    try:
        from pymusixmatch import Musixmatch
    except ImportError:
        return None

    try:
        client = Musixmatch(api_key)
        response = client.matcher_lyrics_get(
            q_track=title,
            q_artist=artist or "",
        )
        body = response.get("message", {}).get("body", {})
        lyrics = body.get("lyrics", {}).get("lyrics_body")
        if not lyrics:
            return None
        lyrics = lyrics.split("******* This Lyrics is NOT for Commercial use *******")[0]
        return lyrics.strip() or None
    except Exception:
        return None
