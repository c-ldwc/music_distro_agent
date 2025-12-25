import sqlite3
from datetime import datetime
from src.classes import track
import hashlib


def get_db_connection(db_path: str = "playlists.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS playlists (
            row_id TEXT PRIMARY KEY,
            id TEXT,
            playlist_id TEXT,
            playlist_name TEXT,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            last_attempt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    return conn


def record_track(conn, release: track, playlist_name: str, playlist_id: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, playlist_id, attempts FROM playlists WHERE id=? and playlist_id=?",
        (release.track_id, playlist_id),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE playlists SET attempts=attempts+1, last_attempt=? WHERE id=? and playlist_id=?",
            (datetime.now(), row[0], row[1]),
        )
    else:
        cur.execute(
            "INSERT INTO playlists (row_id, artist, album, id, playlist_id, playlist_name) VALUES (?, ?, ?, ?, ?, ?)",
            (
                hashlib.sha256(
                    release.track_id.encode() + playlist_id.encode()
                ).hexdigest(),
                release.artist,
                release.album,
                release.track_id,
                playlist_id,
                playlist_name,
            ),
        )
    conn.commit()
