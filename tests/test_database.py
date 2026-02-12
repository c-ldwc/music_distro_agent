"""
Tests for database operations.
"""

import hashlib

from src.classes import track
from src.db.playlist_db import get_db_connection, record_track


class TestDatabaseConnection:
    """Tests for database connection and schema."""

    def test_creates_database(self, temp_dir):
        """Test that database is created with proper schema."""
        db_path = temp_dir / "test.db"
        conn = get_db_connection(str(db_path))

        # Verify database file exists
        assert db_path.exists()

        # Verify schema
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='playlists'")
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "playlists"

        conn.close()

    def test_schema_has_correct_columns(self, temp_dir):
        """Test that table has all required columns."""
        db_path = temp_dir / "test.db"
        conn = get_db_connection(str(db_path))

        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(playlists)")
        columns = {row[1] for row in cursor.fetchall()}

        expected_columns = {
            "row_id",
            "id",
            "playlist_id",
            "playlist_name",
            "artist",
            "album",
            "attempts",
            "last_attempt",
        }
        assert expected_columns.issubset(columns)

        conn.close()


class TestRecordTrack:
    """Tests for recording tracks in the database."""

    def test_insert_new_track(self, temp_database):
        """Test inserting a new track."""
        conn, db_path = temp_database

        test_track = track(artist="Test Artist", album="Test Album", track_id="spotify:track:test123")

        record_track(
            conn,
            test_track,
            playlist_name="Test Playlist",
            playlist_id="test_playlist_id",
        )

        # Verify insertion
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM playlists WHERE id=?", (test_track.track_id,))
        result = cursor.fetchone()

        assert result is not None
        assert result[1] == test_track.track_id  # id column
        assert result[2] == "test_playlist_id"  # playlist_id column
        assert result[3] == "Test Playlist"  # playlist_name column
        assert result[4] == "Test Artist"  # artist column
        assert result[5] == "Test Album"  # album column
        assert result[6] == 0  # attempts column

    def test_duplicate_track_increments_attempts(self, temp_database):
        """Test that duplicate inserts increment attempts."""
        conn, db_path = temp_database

        test_track = track(artist="Test Artist", album="Test Album", track_id="spotify:track:test456")

        # Insert first time
        record_track(
            conn,
            test_track,
            playlist_name="Test Playlist",
            playlist_id="test_playlist_id",
        )

        # Insert duplicate
        record_track(
            conn,
            test_track,
            playlist_name="Test Playlist",
            playlist_id="test_playlist_id",
        )

        # Verify attempts incremented
        cursor = conn.cursor()
        cursor.execute("SELECT attempts FROM playlists WHERE id=?", (test_track.track_id,))
        result = cursor.fetchone()

        assert result[0] == 1  # Should be 1 after one duplicate attempt

    def test_row_id_is_unique_hash(self, temp_database):
        """Test that row_id is a hash of track_id and playlist_id."""
        conn, db_path = temp_database

        test_track = track(artist="Test Artist", album="Test Album", track_id="spotify:track:hash_test")
        playlist_id = "test_playlist_id"

        # Calculate expected hash
        expected_hash = hashlib.sha256((test_track.track_id + playlist_id).encode()).hexdigest()

        record_track(conn, test_track, playlist_name="Test Playlist", playlist_id=playlist_id)

        cursor = conn.cursor()
        cursor.execute("SELECT row_id FROM playlists WHERE id=?", (test_track.track_id,))
        result = cursor.fetchone()

        assert result[0] == expected_hash

    def test_same_track_different_playlists(self, temp_database):
        """Test same track can be in different playlists."""
        conn, db_path = temp_database

        test_track = track(
            artist="Test Artist",
            album="Test Album",
            track_id="spotify:track:multi_playlist",
        )

        # Add to first playlist
        record_track(conn, test_track, playlist_name="Playlist 1", playlist_id="playlist_1")

        # Add to second playlist
        record_track(conn, test_track, playlist_name="Playlist 2", playlist_id="playlist_2")

        # Verify both records exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM playlists WHERE id=?", (test_track.track_id,))
        count = cursor.fetchone()[0]

        assert count == 2
