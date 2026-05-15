import os

from db.database import get_setting


def fetch_lyrics(title, artist):
    token = get_setting("genius_token") or os.environ.get("GENIUS_ACCESS_TOKEN")
    if not token or not title:
        return None

    try:
        import lyricsgenius
    except ImportError:
        return None

    try:
        genius = lyricsgenius.Genius(
            token,
            remove_section_headers=True,
            skip_non_songs=True,
            timeout=10,
            verbose=False,
        )
        song = genius.search_song(title, artist=artist or "")
        lyrics = getattr(song, "lyrics", None) if song else None
        return lyrics.strip() if lyrics else None
    except Exception:
        return None
