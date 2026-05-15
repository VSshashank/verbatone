import os
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "verbatone.sqlite3"


TRACK_FIELDS = [
    "id",
    "title",
    "artist",
    "album",
    "path",
    "duration",
    "cover_art",
    "language",
    "status",
    "ttml_path",
    "vocals_path",
    "instrumental_path",
    "has_phonetics",
    "type",
    "created_at",
]


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tracks (
              id          TEXT PRIMARY KEY,
              title       TEXT,
              artist      TEXT,
              album       TEXT,
              path        TEXT NOT NULL,
              duration    REAL,
              cover_art   TEXT,
              language    TEXT,
              status      TEXT DEFAULT 'unprocessed',
              ttml_path   TEXT,
              vocals_path TEXT,
              instrumental_path TEXT,
              created_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS karaoke_scores (
              id         TEXT PRIMARY KEY,
              track_id   TEXT,
              player     TEXT,
              pitch      INTEGER,
              timing     INTEGER,
              consistency INTEGER,
              completion  INTEGER,
              total       INTEGER,
              played_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_path ON tracks(path);"
        )

        # Phase 3 schema migrations
        if not column_exists(conn, "tracks", "has_phonetics"):
            conn.execute(
                "ALTER TABLE tracks ADD COLUMN has_phonetics INTEGER DEFAULT 0"
            )
        if not column_exists(conn, "tracks", "type"):
            conn.execute(
                "ALTER TABLE tracks ADD COLUMN type TEXT DEFAULT 'music'"
            )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )


def row_to_track(row):
    if row is None:
        return None
    return {field: row[field] for field in TRACK_FIELDS}


def normalize_path(path):
    return os.path.abspath(os.path.expanduser(path))


def find_track_by_path(path):
    normalized = normalize_path(path)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tracks WHERE path = ?",
            (normalized,),
        ).fetchone()
    return row_to_track(row)


def find_track(track_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
    return row_to_track(row)


def update_track(track_id, **updates):
    allowed = set(TRACK_FIELDS) - {"id", "created_at"}
    fields = [field for field in updates if field in allowed]
    if not fields:
        return find_track(track_id)

    assignments = ", ".join([f"{field} = ?" for field in fields])
    values = [updates[field] for field in fields]
    values.append(track_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE tracks SET {assignments} WHERE id = ?",
            values,
        )
        row = conn.execute(
            "SELECT * FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
    return row_to_track(row)


def delete_track(track_id):
    track = find_track(track_id)
    if not track:
        return None
    with get_connection() as conn:
        conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
    return track


def list_tracks():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM tracks ORDER BY datetime(created_at) DESC, title COLLATE NOCASE"
        ).fetchall()
    return [row_to_track(row) for row in rows]


def insert_track(track):
    normalized = {**track, "path": normalize_path(track["path"])}
    fields = [
        "id",
        "title",
        "artist",
        "album",
        "path",
        "duration",
        "cover_art",
        "language",
        "status",
        "ttml_path",
        "vocals_path",
        "instrumental_path",
    ]
    placeholders = ", ".join(["?"] * len(fields))
    columns = ", ".join(fields)
    values = [normalized.get(field) for field in fields]
    with get_connection() as conn:
        conn.execute(
            f"INSERT INTO tracks ({columns}) VALUES ({placeholders})",
            values,
        )
        row = conn.execute(
            "SELECT * FROM tracks WHERE id = ?",
            (normalized["id"],),
        ).fetchone()
    return row_to_track(row)


def get_setting(key, default=None):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
