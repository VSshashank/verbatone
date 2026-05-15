"""
LRCLIB client — fetches pre-synced (LRC) lyrics from https://lrclib.net
No API key required.  Uses only `requests` (already in requirements).
"""
import logging
import re

log = logging.getLogger(__name__)

LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
REQUEST_TIMEOUT = 12

INDIC_LANGUAGES = {"hi", "ta", "te", "kn", "ml", "bn", "pa", "mr", "gu"}


# ---------------------------------------------------------------------------
# Title helpers
# ---------------------------------------------------------------------------

def _strip_feat(title):
    """Remove feat./ft. suffixes so LRCLIB can match the base song title."""
    title = re.sub(r"\s*[\(\[]\s*feat\..*?[\)\]]", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\bft\.\s+.*", "", title, flags=re.IGNORECASE)
    return title.strip()


def _strip_parens(title):
    """Remove everything inside parentheses/brackets."""
    return re.sub(r"\s*[\(\[].*?[\)\]]", "", title).strip()


def _normalize_title(title):
    text = str(title or "").lower()
    text = re.sub(
        r"\s*[\(\[](remaster(ed)?|radio edit|explicit|clean|deluxe).*?[\)\]]",
        "", text, flags=re.IGNORECASE,
    )
    return text.strip()


def _romanize_indic(title):
    """
    Attempt Devanagari → IAST romanization using indic_transliteration.
    Returns None if the library is not installed or the title is not Indic.
    """
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate
        return transliterate(title, sanscript.DEVANAGARI, sanscript.IAST)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score(result, title, artist, duration):
    score = 0
    if result.get("syncedLyrics"):
        score += 100
    elif result.get("plainLyrics"):
        score += 10
    else:
        return -1

    rt = _normalize_title(result.get("trackName", ""))
    qt = _normalize_title(_strip_feat(title))
    if rt == qt:
        score += 20
    elif qt in rt or rt in qt:
        score += 10

    ra = str(result.get("artistName", "")).lower()
    qa = str(artist or "").lower()
    if qa and qa in ra:
        score += 15
    elif ra and ra in qa:
        score += 8

    rd = result.get("duration") or 0
    if duration and rd:
        diff = abs(float(duration) - float(rd))
        if diff <= 2:
            score += 10
        elif diff <= 5:
            score += 5
        elif diff > 30:
            score -= 20
    return score


# ---------------------------------------------------------------------------
# Search helper
# ---------------------------------------------------------------------------

def _search(title, artist, album=None):
    try:
        import requests
    except ImportError:
        return []
    params = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album
    try:
        resp = requests.get(LRCLIB_SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as exc:
        log.debug("lrclib_client search error: %s", exc)
        return []


def _best(results, title, artist, duration):
    scored = []
    for r in results:
        s = _score(r, title, artist, duration)
        if s > 0:
            scored.append((s, r))
    if not scored:
        return None
    return sorted(scored, key=lambda x: x[0], reverse=True)[0][1]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_synced_lyrics(title, artist, album=None, duration=None, language=None):
    """
    Search LRCLIB for synced (LRC) lyrics.

    Returns
    -------
    dict or None
        ``{"synced": "[mm:ss.xx] line\\n...", "plain": "...", "source": "lrclib"}``
        or None.
    """
    if not title:
        return None

    # Build candidate title variants to try in order
    clean = _strip_feat(title)
    bare = _strip_parens(clean)
    variants = list(dict.fromkeys([clean, bare, title]))  # deduplicated, ordered

    # For Indic-script titles, also try romanized form
    if language in INDIC_LANGUAGES or any(ord(c) > 0x0900 for c in title[:20]):
        romanized = _romanize_indic(clean)
        if romanized and romanized != clean:
            variants.append(romanized)

    best = None
    for variant in variants:
        results = _search(variant, artist, album)
        if results:
            candidate = _best(results, title, artist, duration)
            if candidate and (candidate.get("syncedLyrics") or candidate.get("plainLyrics")):
                # Prefer synced; keep looking if we only have plain so far
                if candidate.get("syncedLyrics"):
                    best = candidate
                    break
                elif best is None:
                    best = candidate

    if best is None:
        log.info("lrclib_client: no match for %r by %r", title, artist)
        return None

    synced = (best.get("syncedLyrics") or "").strip() or None
    plain = (best.get("plainLyrics") or "").strip() or None
    log.info(
        "lrclib_client: matched %r by %r  synced=%s",
        best.get("trackName"), best.get("artistName"), bool(synced),
    )
    return {"synced": synced, "plain": plain, "source": "lrclib"}
