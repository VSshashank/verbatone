from dotenv import load_dotenv

load_dotenv()

import mimetypes
import os
import socket
import subprocess
import threading
import time
import wave
import uuid
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from mutagen import File as MutagenFile
from werkzeug.utils import secure_filename

from db.database import (
    delete_track,
    find_track,
    find_track_by_path,
    get_setting,
    init_db,
    insert_karaoke_score,
    insert_track,
    list_tracks,
    normalize_path,
    set_setting,
    update_track,
)
from lyrics.genius_client import fetch_lyrics_result as fetch_genius_lyrics
from lyrics.musixmatch_client import fetch_lyrics_result as fetch_musixmatch_lyrics
from pipeline.demucs_runner import separate as separate_stems
from pipeline.phonetics import romanize_words
from pipeline.ttml_generator import generate_ttml
from pipeline.whisperx_runner import align as align_words
from pipeline.whisperx_runner import transcribe as transcribe_words
from scoring.karaoke_scorer import score as score_karaoke


SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg"}
DATA_DIR = Path(__file__).resolve().parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TTML_DIR = DATA_DIR / "ttml"
COVERS_DIR = DATA_DIR / "covers"
STEMS_DIR = DATA_DIR / "stems"
KARAOKE_DIR = DATA_DIR / "karaoke"
BACKEND_PORT = int(os.environ.get("VERBATONE_BACKEND_PORT", "5051"))
ALIGNMENT_JOBS = {}
STEM_JOBS = {}
KARAOKE_SUBMISSION = {
    "ready": False,
    "track_id": None,
    "webm_path": None,
    "wav_path": None,
    "score": None,
    "error": None,
    "submitted_at": None,
}
PHONETIC_LANGUAGES = {"hi", "kn", "ta", "te", "ml", "mr", "gu", "pa"}

app = Flask(__name__)
CORS(app)
init_db()


@app.before_request
def ensure_database_schema():
    init_db()


def is_audio_file(path):
    return Path(path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def first_value(value):
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def read_tag(audio, *keys):
    if not audio or not audio.tags:
        return None
    for key in keys:
        if key in audio.tags:
            return first_value(audio.tags.get(key))
    return None


def read_cover_art(audio):
    """Return (bytes, mime_type) for embedded cover art, or (None, None)."""
    if not audio or not audio.tags:
        return None, None

    tags = audio.tags

    for key in tags.keys():
        if str(key).startswith("APIC"):
            image = tags[key]
            data = getattr(image, "data", None)
            mime = getattr(image, "mime", "image/jpeg")
            if data:
                return data, mime

    pictures = getattr(audio, "pictures", None)
    if pictures:
        picture = pictures[0]
        return picture.data, picture.mime

    cover = tags.get("covr")
    if cover:
        cover_data = cover[0] if isinstance(cover, list) else cover
        image_format = getattr(cover_data, "imageformat", None)
        mime = "image/png" if image_format == 14 else "image/jpeg"
        return bytes(cover_data), mime

    return None, None


def save_cover_art(track_id, data, mime):
    """Write cover art bytes to disk and return the serving URL."""
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    ext = "png" if "png" in mime else "jpg"
    path = COVERS_DIR / f"{track_id}.{ext}"
    path.write_bytes(data)
    return f"/api/cover/{track_id}"


def metadata_for_file(path):
    audio = MutagenFile(path)
    title = read_tag(audio, "title", "TIT2", "\xa9nam") or Path(path).stem
    artist = read_tag(audio, "artist", "TPE1", "\xa9ART") or "Unknown Artist"
    album = read_tag(audio, "album", "TALB", "\xa9alb") or "Unknown Album"
    duration = None
    if audio and audio.info and getattr(audio.info, "length", None):
        duration = round(float(audio.info.length), 3)
    elif Path(path).suffix.lower() == ".wav":
        try:
            with wave.open(path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = round(frames / float(rate), 3) if rate else None
        except wave.Error:
            duration = None

    track_id = str(uuid.uuid4())
    cover_art_url = None
    cover_data, cover_mime = read_cover_art(audio)
    if cover_data:
        cover_art_url = save_cover_art(track_id, cover_data, cover_mime)

    return {
        "id": track_id,
        "title": title,
        "artist": artist,
        "album": album,
        "path": normalize_path(path),
        "duration": duration,
        "cover_art": cover_art_url,
        "language": None,
        "status": "unprocessed",
        "ttml_path": None,
        "vocals_path": None,
        "instrumental_path": None,
    }


def discover_audio_files(path):
    root = Path(normalize_path(path))
    if root.is_file():
        return [root] if is_audio_file(root) else []
    return sorted(
        [item for item in root.rglob("*") if item.is_file() and is_audio_file(item)],
        key=lambda item: str(item).lower(),
    )


def safe_upload_relative_path(filename):
    parts = [secure_filename(part) for part in filename.replace("\\", "/").split("/")]
    parts = [part for part in parts if part and part not in {".", ".."}]
    if not parts:
        return Path(f"audio-{uuid.uuid4().hex}")
    return Path(*parts)


def import_file_at_path(audio_path):
    audio_path_string = str(audio_path)
    existing = find_track_by_path(audio_path_string)
    if existing:
        return None, {"path": audio_path_string, "reason": "already_imported"}, None

    try:
        return insert_track(metadata_for_file(audio_path_string)), None, None
    except Exception as exc:
        return None, None, {"path": audio_path_string, "error": str(exc)}


def fetch_lyrics_for_track(track):
    errors = []

    genius_result = fetch_genius_lyrics(track.get("title"), track.get("artist"))
    if genius_result.get("lyrics"):
        return genius_result["lyrics"], "genius", errors
    if genius_result.get("error"):
        errors.append({"source": "genius", "message": genius_result["error"]})

    musixmatch_result = fetch_musixmatch_lyrics(track.get("title"), track.get("artist"))
    if musixmatch_result.get("lyrics"):
        return musixmatch_result["lyrics"], "musixmatch", errors
    if musixmatch_result.get("error"):
        errors.append({"source": "musixmatch", "message": musixmatch_result["error"]})

    return None, None, errors


def path_inside_data_dir(path):
    if not path:
        return False
    try:
        Path(path).resolve().relative_to(DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def remove_file_if_safe(path):
    if not path:
        return
    candidate = Path(path)
    if candidate.exists() and path_inside_data_dir(candidate):
        candidate.unlink()


def remove_track_artifacts(track, delete_audio=False):
    remove_file_if_safe(track.get("ttml_path"))
    remove_file_if_safe(track.get("vocals_path"))
    remove_file_if_safe(track.get("instrumental_path"))
    if delete_audio:
        remove_file_if_safe(track.get("path"))
    for ext in ["jpg", "png"]:
        remove_file_if_safe(COVERS_DIR / f"{track['id']}.{ext}")


def audio_mime_type(path):
    suffix = Path(path).suffix.lower()
    if suffix in {".m4a", ".mp4"}:
        return "audio/mp4"
    if suffix == ".aac":
        return "audio/aac"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".flac":
        return "audio/flac"
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def serve_audio_file(path):
    return send_file(
        path,
        mimetype=audio_mime_type(path),
        conditional=True,
        etag=True,
        last_modified=os.path.getmtime(path),
    )


def local_network_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def stem_state(track):
    if not track:
        return {"status": "missing"}
    if track.get("vocals_path") and track.get("instrumental_path"):
        if os.path.exists(track["vocals_path"]) and os.path.exists(track["instrumental_path"]):
            return {
                "status": "ready",
                "vocals_url": f"/api/stems/{track['id']}/vocals",
                "instrumental_url": f"/api/stems/{track['id']}/instrumental",
                "track": track,
            }
    job = STEM_JOBS.get(track["id"])
    if job:
        return {"status": job.get("status", "processing"), "error": job.get("error"), "track": track}
    return {"status": "unprepared", "track": track}


def run_stem_job(track_id):
    STEM_JOBS[track_id] = {"status": "processing", "error": None}
    try:
        track = find_track(track_id)
        if not track:
            STEM_JOBS[track_id] = {"status": "error", "error": "Track not found."}
            return
        if not os.path.exists(track["path"]):
            STEM_JOBS[track_id] = {"status": "error", "error": "Audio file is missing."}
            return

        output_dir = STEMS_DIR / track_id
        stems = separate_stems(track["path"], output_dir)
        updated = update_track(
            track_id,
            status="karaoke_ready",
            vocals_path=stems["vocals"],
            instrumental_path=stems["no_vocals"],
        )
        STEM_JOBS[track_id] = {"status": "ready", "error": None, "track": updated}
    except Exception as exc:
        STEM_JOBS[track_id] = {"status": "error", "error": str(exc)}


def run_alignment_job(track_id, lyrics_text=None, language=None):
    ALIGNMENT_JOBS[track_id] = {"status": "aligning", "error": None}
    try:
        track = find_track(track_id)
        if not track:
            ALIGNMENT_JOBS[track_id] = {"status": "error", "error": "Track not found."}
            return

        text = (lyrics_text or "").strip()
        if not text:
            update_track(track_id, status="fetching_lyrics")
            text, _source, lyric_errors = fetch_lyrics_for_track(track)

        if not text:
            error_message = "No lyrics were found. Add lyrics manually to align this track."
            if "lyric_errors" in locals() and lyric_errors:
                error_message = lyric_errors[0]["message"]
            update_track(track_id, status="needs_review")
            ALIGNMENT_JOBS[track_id] = {
                "status": "needs_review",
                "error": error_message,
            }
            return

        # Pattern C: use clean vocals stem for alignment when available
        vocals_path = track.get("vocals_path")
        if vocals_path and not os.path.exists(vocals_path):
            vocals_path = None

        update_track(track_id, status="aligning")
        result = align_words(
            track["path"],
            lyrics_text=text,
            language=language,
            vocals_path=vocals_path,
        )
        words = result.get("words", [])
        transcript_segments = result.get("segments", [])
        detected_language = result.get("language") or language
        if not words:
            update_track(track_id, status="needs_review", language=detected_language)
            ALIGNMENT_JOBS[track_id] = {
                "status": "needs_review",
                "error": "No word timestamps were produced.",
            }
            return

        # Phonetic romanization for supported Indic languages
        needs_phonetics = (detected_language or "").lower() in PHONETIC_LANGUAGES
        if needs_phonetics:
            words = romanize_words(words, detected_language)

        TTML_DIR.mkdir(parents=True, exist_ok=True)
        ttml_path = TTML_DIR / f"{track_id}.ttml"
        ttml_path.write_text(
            generate_ttml(
                words,
                lyrics_text=text,
                language=detected_language,
                include_phonetics=needs_phonetics,
                transcript_segments=transcript_segments,
            ),
            encoding="utf-8",
        )
        updated = update_track(
            track_id,
            status="ready",
            language=detected_language,
            ttml_path=str(ttml_path),
            has_phonetics=1 if needs_phonetics else 0,
        )
        ALIGNMENT_JOBS[track_id] = {"status": "ready", "error": None, "track": updated}
    except Exception as exc:
        update_track(track_id, status="needs_review")
        ALIGNMENT_JOBS[track_id] = {"status": "needs_review", "error": str(exc)}


def run_podcast_transcription_job(track_id, language=None):
    ALIGNMENT_JOBS[track_id] = {"status": "aligning", "error": None}
    try:
        track = find_track(track_id)
        if not track:
            ALIGNMENT_JOBS[track_id] = {"status": "error", "error": "Track not found."}
            return

        update_track(track_id, status="aligning")
        result = transcribe_words(track["path"], language=language)
        words = result.get("words", [])
        detected_language = result.get("language") or language or "en"

        if not words:
            update_track(track_id, status="needs_review", language=detected_language)
            ALIGNMENT_JOBS[track_id] = {
                "status": "needs_review",
                "error": "No words were transcribed.",
            }
            return

        TTML_DIR.mkdir(parents=True, exist_ok=True)
        ttml_path = TTML_DIR / f"{track_id}.ttml"
        ttml_path.write_text(
            generate_ttml(words, language=detected_language),
            encoding="utf-8",
        )
        updated = update_track(
            track_id,
            status="ready",
            language=detected_language,
            ttml_path=str(ttml_path),
        )
        ALIGNMENT_JOBS[track_id] = {"status": "ready", "error": None, "track": updated}
    except Exception as exc:
        update_track(track_id, status="needs_review")
        ALIGNMENT_JOBS[track_id] = {"status": "needs_review", "error": str(exc)}


@app.route("/api/import", methods=["POST"])
def import_audio():
    payload = request.get_json(silent=True) or {}
    requested_path = payload.get("path")
    if not requested_path:
        return jsonify({"error": "A local file or folder path is required."}), 400

    normalized = normalize_path(requested_path)
    if not os.path.exists(normalized):
        return jsonify({"error": f"Path does not exist: {normalized}"}), 400

    imported = []
    skipped = []
    errors = []

    for audio_path in discover_audio_files(normalized):
        imported_track, skipped_item, error_item = import_file_at_path(audio_path)
        if imported_track:
            imported.append(imported_track)
        if skipped_item:
            skipped.append(skipped_item)
        if error_item:
            errors.append(error_item)

    return jsonify({"imported": imported, "skipped": skipped, "errors": errors})


@app.route("/api/import-upload", methods=["POST"])
def import_uploaded_audio():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Choose at least one audio file."}), 400

    imported = []
    skipped = []
    errors = []
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for uploaded_file in files:
        original_name = uploaded_file.filename or ""
        if not original_name or not is_audio_file(original_name):
            skipped.append({"path": original_name, "reason": "unsupported_file_type"})
            continue

        relative_path = safe_upload_relative_path(original_name)
        destination = UPLOAD_DIR / relative_path

        existing = find_track_by_path(str(destination))
        if existing:
            skipped.append({"path": str(destination), "reason": "already_imported"})
            continue

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            uploaded_file.save(destination)
            imported_track, skipped_item, error_item = import_file_at_path(destination)
            if imported_track:
                imported.append(imported_track)
            if skipped_item:
                skipped.append(skipped_item)
            if error_item:
                errors.append(error_item)
        except Exception as exc:
            errors.append({"path": original_name, "error": str(exc)})

    return jsonify({"imported": imported, "skipped": skipped, "errors": errors})


@app.route("/api/lyrics/fetch", methods=["GET"])
def fetch_lyrics():
    track_id = request.args.get("track_id")
    if not track_id:
        return jsonify({"error": "track_id is required."}), 400

    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    lyrics, source, errors = fetch_lyrics_for_track(track)
    message = None
    if not lyrics:
        message = errors[0]["message"] if errors else "No lyrics found. Paste lyrics manually to align this track."
    return jsonify({"lyrics": lyrics, "source": source, "errors": errors, "message": message})


@app.route("/api/align", methods=["POST"])
def align_track():
    payload = request.get_json(silent=True) or {}
    track_id = payload.get("track_id")
    if not track_id:
        return jsonify({"error": "track_id is required."}), 400

    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    lyrics_text = payload.get("lyrics_text")
    language = payload.get("language")
    update_track(track_id, status="aligning")
    thread = threading.Thread(
        target=run_alignment_job,
        args=(track_id, lyrics_text, language),
        daemon=True,
    )
    thread.start()
    return jsonify({"track": find_track(track_id), "status": "aligning"})


@app.route("/api/transcribe", methods=["POST"])
def transcribe_podcast():
    """
    Transcribe a podcast or speech file to word-synced TTML subtitles.
    Unlike /api/align, this skips lyrics fetching and uses pure transcription.
    """
    payload = request.get_json(silent=True) or {}
    track_id = payload.get("track_id")
    if not track_id:
        return jsonify({"error": "track_id is required."}), 400

    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    language = payload.get("language")
    update_track(track_id, status="aligning")
    thread = threading.Thread(
        target=run_podcast_transcription_job,
        args=(track_id, language),
        daemon=True,
    )
    thread.start()
    return jsonify({"track": find_track(track_id), "status": "aligning"})


@app.route("/api/align/status/<track_id>", methods=["GET"])
def align_status(track_id):
    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404
    job = ALIGNMENT_JOBS.get(track_id, {"status": track["status"], "error": None})
    return jsonify({"track": track, **job})


@app.route("/api/library", methods=["GET"])
def library():
    return jsonify(list_tracks())


@app.route("/api/track/<track_id>", methods=["GET"])
def track(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404
    return jsonify(found)


@app.route("/api/track/<track_id>", methods=["DELETE"])
def delete_track_route(track_id):
    track = delete_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    delete_audio = request.args.get("delete_file") == "1" or path_inside_data_dir(track.get("path"))
    remove_track_artifacts(track, delete_audio=delete_audio)
    ALIGNMENT_JOBS.pop(track_id, None)
    return jsonify({"ok": True, "deleted": track_id})


@app.route("/api/track/<track_id>/type", methods=["POST"])
def set_track_type(track_id):
    payload = request.get_json(silent=True) or {}
    track_type = payload.get("type")
    if track_type not in {"music", "podcast"}:
        return jsonify({"error": "type must be 'music' or 'podcast'"}), 400
    updated = update_track(track_id, type=track_type)
    if not updated:
        return jsonify({"error": "Track not found."}), 404
    return jsonify(updated)


@app.route("/api/ttml/<track_id>", methods=["DELETE"])
def delete_ttml(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404

    remove_file_if_safe(found.get("ttml_path"))
    ALIGNMENT_JOBS.pop(track_id, None)
    updated = update_track(
        track_id,
        status="unprocessed",
        ttml_path=None,
        language=None,
        has_phonetics=0,
    )
    return jsonify(updated)


@app.route("/api/ttml/<track_id>", methods=["GET"])
def ttml(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404

    ttml_path = found.get("ttml_path")
    if not ttml_path or not os.path.exists(ttml_path):
        return jsonify({"error": "TTML has not been generated for this track."}), 404

    return send_file(ttml_path, mimetype="application/ttml+xml")


@app.route("/api/debug/ttml/<track_id>", methods=["GET"])
def debug_ttml(track_id):
    """Return all word timestamps from a track's TTML as JSON for diagnosis."""
    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    ttml_path = track.get("ttml_path")
    if not ttml_path or not os.path.exists(ttml_path):
        return jsonify({"error": "No TTML file exists for this track."}), 404

    import xml.etree.ElementTree as ET

    tree = ET.parse(ttml_path)
    ns = {"tt": "http://www.w3.org/ns/ttml"}
    words = []
    for span in tree.findall(".//tt:span[@begin]", ns):
        words.append(
            {
                "word": span.text.strip() if span.text else "",
                "start": span.get("begin"),
                "end": span.get("end"),
            }
        )
    return jsonify(words)


@app.route("/api/debug/alignment/<track_id>", methods=["GET"])
def debug_alignment(track_id):
    """
    Analyse an aligned track's TTML and classify the timestamp pattern.

    Returns word list, gap statistics, and a pattern classification:
      - pattern_a: timestamps bunched early (segment coverage issue)
      - pattern_b: large gaps / long held words (melisma)
      - pattern_c: missing words (whisperx failed to detect vocals)
      - ok: no obvious issues detected
    """
    track = find_track(track_id)
    if not track:
        return jsonify({"error": "Track not found."}), 404

    ttml_path = track.get("ttml_path")
    if not ttml_path or not os.path.exists(ttml_path):
        return jsonify({"error": "No TTML file exists for this track."}), 404

    import xml.etree.ElementTree as ET

    def _ttml_time_to_seconds(value):
        if not value:
            return 0.0
        parts = value.split(":")
        if len(parts) != 3:
            return float(value or 0)
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)

    tree = ET.parse(ttml_path)
    ns = {"tt": "http://www.w3.org/ns/ttml"}
    words = []
    for span in tree.findall(".//tt:span[@begin]", ns):
        text = span.text.strip() if span.text else ""
        if not text:
            continue
        words.append(
            {
                "word": text,
                "start": _ttml_time_to_seconds(span.get("begin")),
                "end": _ttml_time_to_seconds(span.get("end")),
            }
        )

    if not words:
        return jsonify({"pattern": "pattern_c", "reason": "no words in TTML", "words": []})

    # Compute gap and duration stats
    durations = [w["end"] - w["start"] for w in words]
    gaps = [
        words[i + 1]["start"] - words[i]["end"]
        for i in range(len(words) - 1)
    ]
    audio_duration = track.get("duration") or 0
    last_word_end = words[-1]["end"]
    coverage = last_word_end / audio_duration if audio_duration else 1.0

    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    max_gap = max(gaps) if gaps else 0
    max_duration = max(durations) if durations else 0
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Classify pattern
    pattern = "ok"
    reason = "timestamps look normal"

    if coverage < 0.5 and audio_duration > 30:
        pattern = "pattern_a"
        reason = (
            f"Words only cover {coverage:.0%} of audio duration "
            f"({last_word_end:.1f}s / {audio_duration:.1f}s). "
            f"Timestamps are bunched early."
        )
    elif max_duration > 3.0 or max_gap > 4.0:
        pattern = "pattern_b"
        reason = (
            f"Long held note ({max_duration:.1f}s) or large gap ({max_gap:.1f}s) detected. "
            f"Likely melisma / slow tempo."
        )

    return jsonify(
        {
            "pattern": pattern,
            "reason": reason,
            "word_count": len(words),
            "audio_duration": audio_duration,
            "coverage": round(coverage, 3),
            "stats": {
                "avg_word_duration": round(avg_duration, 3),
                "max_word_duration": round(max_duration, 3),
                "avg_gap": round(avg_gap, 3),
                "max_gap": round(max_gap, 3),
            },
            "words": words,
        }
    )


@app.route("/api/cover/<track_id>", methods=["GET"])
def cover(track_id):
    for ext in ["jpg", "png"]:
        path = COVERS_DIR / f"{track_id}.{ext}"
        if path.exists():
            return send_file(path)
    return "", 404


@app.route("/api/audio/<track_id>", methods=["GET"])
def audio(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404

    audio_path = found["path"]
    if not os.path.exists(audio_path):
        return jsonify({"error": "Audio file no longer exists at its original path."}), 404

    return serve_audio_file(audio_path)


@app.route("/api/stems/<track_id>", methods=["GET"])
def stems(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404
    return jsonify(stem_state(found))


@app.route("/api/stems/<track_id>/prepare", methods=["POST"])
def prepare_stems(track_id):
    found = find_track(track_id)
    if not found:
        return jsonify({"error": "Track not found."}), 404
    state = stem_state(found)
    if state["status"] == "ready":
        return jsonify(state)
    if state["status"] == "processing":
        return jsonify(state), 202

    thread = threading.Thread(target=run_stem_job, args=(track_id,), daemon=True)
    thread.start()
    return jsonify({"status": "processing", "track": find_track(track_id)}), 202


@app.route("/api/stems/<track_id>/vocals", methods=["GET"])
def stem_vocals(track_id):
    found = find_track(track_id)
    if not found or not found.get("vocals_path") or not os.path.exists(found["vocals_path"]):
        return jsonify({"error": "Vocals stem is not ready."}), 404
    return serve_audio_file(found["vocals_path"])


@app.route("/api/stems/<track_id>/instrumental", methods=["GET"])
def stem_instrumental(track_id):
    found = find_track(track_id)
    if not found or not found.get("instrumental_path") or not os.path.exists(found["instrumental_path"]):
        return jsonify({"error": "Instrumental stem is not ready."}), 404
    return serve_audio_file(found["instrumental_path"])


@app.route("/mic", methods=["GET"])
def mic_page():
    return send_file(Path(__file__).resolve().parent / "mic" / "templates" / "mic.html")


@app.route("/api/karaoke/qr", methods=["GET"])
def karaoke_qr():
    try:
        import qrcode
    except ImportError:
        return jsonify({"error": "QR generation needs qrcode[pil]. Install backend requirements first."}), 500

    track_id = request.args.get("track_id")
    url = f"http://{local_network_ip()}:{BACKEND_PORT}/mic"
    if track_id:
        url = f"{url}?track_id={track_id}"
    img = qrcode.make(url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.route("/api/karaoke/reset", methods=["POST"])
def karaoke_reset():
    payload = request.get_json(silent=True) or {}
    for key in ["webm_path", "wav_path"]:
        remove_file_if_safe(KARAOKE_SUBMISSION.get(key))
    KARAOKE_SUBMISSION.update({
        "ready": False,
        "track_id": payload.get("track_id"),
        "webm_path": None,
        "wav_path": None,
        "score": None,
        "error": None,
        "submitted_at": None,
    })
    return jsonify({"ok": True, "ready": False})


@app.route("/api/karaoke/submit", methods=["POST"])
def karaoke_submit():
    track_id = request.args.get("track_id") or request.form.get("track_id")
    KARAOKE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time() * 1000)
    webm_path = KARAOKE_DIR / f"received_{timestamp}.webm"
    wav_path = KARAOKE_DIR / f"received_{timestamp}.wav"

    try:
        webm_path.write_bytes(request.get_data())
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(webm_path), str(wav_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        KARAOKE_SUBMISSION.update({
            "ready": True,
            "track_id": track_id,
            "webm_path": str(webm_path),
            "wav_path": str(wav_path),
            "score": None,
            "error": None,
            "submitted_at": timestamp,
        })
        return jsonify({"ok": True, "ready": True})
    except Exception as exc:
        KARAOKE_SUBMISSION.update({
            "ready": False,
            "track_id": track_id,
            "webm_path": str(webm_path),
            "wav_path": None,
            "score": None,
            "error": str(exc),
            "submitted_at": timestamp,
        })
        return jsonify({"error": str(exc)}), 500


@app.route("/api/karaoke/status", methods=["GET"])
def karaoke_status():
    return jsonify({
        "ready": KARAOKE_SUBMISSION["ready"],
        "track_id": KARAOKE_SUBMISSION["track_id"],
        "error": KARAOKE_SUBMISSION["error"],
        "score": KARAOKE_SUBMISSION["score"],
    })


@app.route("/api/score", methods=["GET", "POST"])
def score_submission():
    payload = request.get_json(silent=True) or {}
    track_id = payload.get("track_id") or request.args.get("track_id") or KARAOKE_SUBMISSION.get("track_id")
    player = payload.get("player") or request.args.get("player") or "Solo"
    track = find_track(track_id) if track_id else None
    if not track:
        return jsonify({"error": "Track not found for scoring."}), 404
    if not KARAOKE_SUBMISSION.get("ready") or not KARAOKE_SUBMISSION.get("wav_path"):
        return jsonify({"error": "No karaoke recording is ready yet."}), 400
    if not track.get("vocals_path") or not os.path.exists(track["vocals_path"]):
        return jsonify({"error": "Vocals stem is not ready for this track."}), 400

    result = score_karaoke(track["vocals_path"], KARAOKE_SUBMISSION["wav_path"])
    insert_karaoke_score(track["id"], result, player=player)
    KARAOKE_SUBMISSION["score"] = result
    return jsonify({"score": result})


@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "genius_token": bool(get_setting("genius_token")),
        "musixmatch_key": bool(get_setting("musixmatch_key")),
    })


@app.route("/api/settings", methods=["POST"])
def save_settings():
    payload = request.get_json(silent=True) or {}
    if "genius_token" in payload:
        set_setting("genius_token", str(payload["genius_token"]).strip())
    if "musixmatch_key" in payload:
        set_setting("musixmatch_key", str(payload["musixmatch_key"]).strip())
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=BACKEND_PORT, debug=False)
