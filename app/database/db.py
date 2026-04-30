import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH

CREATE_SPEAKERS = """
CREATE TABLE IF NOT EXISTS speakers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embedding_count INTEGER DEFAULT 1,
    sample_audio_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    language_hint TEXT DEFAULT 'auto'
);
"""

CREATE_RECORDINGS = """
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_path TEXT NOT NULL,
    processed_path TEXT,
    duration_seconds REAL,
    language_detected TEXT,
    speaker_count INTEGER,
    status TEXT DEFAULT 'uploaded',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
"""

CREATE_SEGMENTS = """
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id),
    speaker_id INTEGER REFERENCES speakers(id),
    raw_speaker_label TEXT,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL
);
"""

CREATE_RECORDING_SPEAKERS = """
CREATE TABLE IF NOT EXISTS recording_speakers (
    recording_id INTEGER NOT NULL,
    raw_label TEXT NOT NULL,
    speaker_id INTEGER REFERENCES speakers(id),
    match_confidence REAL,
    confirmed_by_user INTEGER DEFAULT 0,
    PRIMARY KEY (recording_id, raw_label)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute(CREATE_SPEAKERS)
        conn.execute(CREATE_RECORDINGS)
        conn.execute(CREATE_SEGMENTS)
        conn.execute(CREATE_RECORDING_SPEAKERS)
