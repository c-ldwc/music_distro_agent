import hashlib
import sqlite3
from datetime import datetime

from src.classes import track
from src.utils import is_valid_spotify_id

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS album_mappings (
            mapping_id TEXT PRIMARY KEY,
            extracted_artist TEXT NOT NULL,
            extracted_album TEXT NOT NULL,
            playlist_id TEXT NOT NULL,
            spotify_artist TEXT NOT NULL,
            spotify_album TEXT NOT NULL,
            spotify_album_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    return conn


def drop_playlist(conn, playlist_name:str | None, playlist_id: str | None):
    if not (playlist_id or playlist_name):
        raise RuntimeError("Please provide a playlist_name or playlist_id")
    cur = conn.cursor()
    if playlist_id and playlist_name:
        cur.execute("Select distinct playlist_name from playlists where playlist_id=?", (playlist_id))
        row = cur.fetchone()
        if row[0] != playlist_name:
            raise RuntimeError(f"The playliist with id {playlist_id} has name {row[0]} which is not the playlist_name provided ({playlist_name})")
    if playlist_id:
        cur.execute("Delete from playlists where playlist_id=?", playlist_id)

    if playlist_name:
        cur.execute("Delete from playlists where playlist_name=?", playlist_name)
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


def get_album_mapping(conn, extracted_artist: str, extracted_album: str, playlist_id: str) -> dict | None:
    """
    Get the Spotify album mapping for a previously searched album.
    
    Args:
        conn: Database connection
        extracted_artist: Artist name as extracted from email (comma-separated)
        extracted_album: Album name as extracted from email
        playlist_id: Spotify playlist ID
        
    Returns:
        Dict with spotify_artist, spotify_album, and spotify_album_id if found, None otherwise
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT spotify_artist, spotify_album, spotify_album_id 
           FROM album_mappings 
           WHERE extracted_artist=? AND extracted_album=? AND playlist_id=?""",
        (extracted_artist, extracted_album, playlist_id),
    )
    row = cur.fetchone()
    if row:
        return {
            "spotify_artist": row[0],
            "spotify_album": row[1],
            "spotify_album_id": row[2],
        }
    return None


def record_album_mapping(
    conn,
    extracted_artist: str,
    extracted_album: str,
    playlist_id: str,
    spotify_artist: str,
    spotify_album: str,
    spotify_album_id: str,
):
    """
    Record a mapping between extracted names and Spotify album details.
    
    Args:
        conn: Database connection
        extracted_artist: Artist name as extracted from email (comma-separated)
        extracted_album: Album name as extracted from email
        playlist_id: Spotify playlist ID
        spotify_artist: Artist name from Spotify (comma-separated)
        spotify_album: Album name from Spotify
        spotify_album_id: Spotify album ID
    """
    # Validate Spotify ID before storing
    if not is_valid_spotify_id(spotify_album_id):
        raise ValueError(f"Invalid Spotify album ID: '{spotify_album_id}' - must be 22 alphanumeric characters")
    
    cur = conn.cursor()
    mapping_id = hashlib.sha256(
        (extracted_artist + extracted_album + playlist_id).encode()
    ).hexdigest()
    
    # Use INSERT OR REPLACE to handle duplicates
    cur.execute(
        """INSERT OR REPLACE INTO album_mappings 
           (mapping_id, extracted_artist, extracted_album, playlist_id, 
            spotify_artist, spotify_album, spotify_album_id, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            mapping_id,
            extracted_artist,
            extracted_album,
            playlist_id,
            spotify_artist,
            spotify_album,
            spotify_album_id,
            datetime.now(),
        ),
    )
    conn.commit()
