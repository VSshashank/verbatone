import os
import re

from db.database import get_setting


GENIUS_SEARCH_URL = "https://api.genius.com/search"


def clean_token(value):
    token = (value or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def clean_lyrics(lyrics, title=None):
    if not lyrics:
        return None

    title_words = re.sub(r"\W+", "", title or "").lower()
    lines = []
    previous_blank = False

    for index, raw_line in enumerate(str(lyrics).replace("\r\n", "\n").split("\n")):
        line = raw_line.strip()

        if not line:
            if lines and not previous_blank:
                lines.append("")
                previous_blank = True
            continue

        compact = re.sub(r"\W+", "", line).lower()
        lowered = line.lower()

        if index == 0 and lowered.endswith("lyrics") and title_words and title_words in compact:
            continue
        if lowered.startswith(("you might also like", "see ", "get tickets")):
            continue

        line = re.sub(r"\d*embed$", "", line, flags=re.IGNORECASE).strip()
        if not line:
            continue

        lines.append(line)
        previous_blank = False

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    return "\n".join(lines).strip() or None


def provider_result(lyrics=None, error=None, detail=None):
    return {
        "lyrics": lyrics,
        "source": "genius" if lyrics else None,
        "error": error,
        "detail": detail,
    }


def best_hit(hits, title, artist):
    if not hits:
        return None

    wanted_artist = (artist or "").strip().lower()
    wanted_title = re.sub(r"\s+", " ", title or "").strip().lower()

    def score(hit):
        result = hit.get("result", {})
        primary_artist = result.get("primary_artist", {}).get("name", "").lower()
        full_title = result.get("full_title", "").lower()
        score_value = 0
        if wanted_artist and wanted_artist in primary_artist:
            score_value += 3
        if wanted_title and wanted_title in full_title:
            score_value += 2
        if result.get("url"):
            score_value += 1
        return score_value

    return sorted(hits, key=score, reverse=True)[0].get("result")


def fetch_lyrics_result(title, artist):
    token = clean_token(get_setting("genius_token") or os.environ.get("GENIUS_ACCESS_TOKEN"))
    if not token:
        return provider_result(error="No Genius token is saved.")
    if not title:
        return provider_result(error="This track has no title to search.")

    try:
        import requests
        import lyricsgenius
    except ImportError as exc:
        return provider_result(error="Genius lyrics dependencies are not installed.", detail=str(exc))

    try:
        response = requests.get(
            GENIUS_SEARCH_URL,
            headers={"Authorization": f"Bearer {token}"},
            params={"q": " ".join(part for part in [title, artist] if part)},
            timeout=12,
        )
        if response.status_code in {401, 403}:
            return provider_result(error="The saved Genius token was rejected. Paste a valid Client Access Token.")
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("response", {}).get("hits", [])
        hit = best_hit(hits, title, artist)
        if not hit:
            return provider_result(error="Genius did not find a matching song.")

        genius = lyricsgenius.Genius(
            token,
            remove_section_headers=False,
            skip_non_songs=True,
            timeout=12,
            verbose=False,
        )
        lyrics = genius.lyrics(song_url=hit.get("url"))
        cleaned = clean_lyrics(lyrics, title=title)
        if cleaned:
            return provider_result(lyrics=cleaned)
        return provider_result(error="Genius found the song, but no lyrics text was returned.")
    except requests.RequestException as exc:
        return provider_result(error="Could not reach Genius right now.", detail=str(exc))
    except Exception as exc:
        return provider_result(error="Genius lyrics fetch failed.", detail=str(exc))


def fetch_lyrics(title, artist):
    return fetch_lyrics_result(title, artist).get("lyrics")
