"""
Pytest configuration and shared fixtures.
"""

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_email_data():
    """Sample email data for testing."""
    return {
        "date": "2026-02-05T10:00:00",
        "body": """
        New Releases This Week:

        1. Floating Points - Cascade (Album)
        2. Aphex Twin - Selected Ambient Works Volume II (Reissue)
        3. Four Tet - Three (EP)
        4. Burial - Antidawn (Album)
        5. The Field - Looping State of Mind (Album)
        """,
    }


@pytest.fixture
def sample_email_file(temp_dir, sample_email_data):
    """Create a sample email file for testing."""
    email_file = temp_dir / "attach_1.txt"
    with open(email_file, "w") as f:
        json.dump(sample_email_data, f)
    return email_file


@pytest.fixture
def sample_extraction_results():
    """Sample extraction results from AI agent."""
    return [
        {"artist": ["Floating Points"], "album": "Cascade"},
        {"artist": ["Aphex Twin"], "album": "Selected Ambient Works Volume II"},
        {"artist": ["Four Tet"], "album": "Three"},
        {"artist": ["Burial"], "album": "Antidawn"},
        {"artist": ["The Field"], "album": "Looping State of Mind"},
    ]


@pytest.fixture
def sample_spotify_search_results():
    """Sample Spotify search API results."""
    return [
        {
            "artists": ["Floating Points"],
            "title": "Cascade",
            "id": "spotify:album:abc123",
        },
        {
            "artists": ["Aphex Twin"],
            "title": "Selected Ambient Works Volume II",
            "id": "spotify:album:def456",
        },
    ]


@pytest.fixture
def temp_database(temp_dir):
    """Create a temporary test database."""
    db_path = temp_dir / "test.db"
    conn = sqlite3.connect(str(db_path))

    # Create schema
    conn.execute("""
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
    """)
    conn.commit()

    yield conn, db_path

    conn.close()


@pytest.fixture
def mock_env_file(temp_dir, monkeypatch):
    """Create a mock .env file for testing."""
    env_file = temp_dir / ".env"
    env_content = """
SPOTIFY_CLIENT_ID=test_client_id
SPOTIFY_CLIENT_SECRET=test_client_secret
SPOTIFY_SCOPES=playlist-modify-public,playlist-modify-private

ANTHROPIC_API_KEY=test_api_key_12345

GMAIL_SECRET_PATH=client_secret_test.json
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly

EMAIL_PATH=test_emails
DATABASE_PATH=test.db
"""
    env_file.write_text(env_content)

    # Change working directory for tests
    monkeypatch.chdir(temp_dir)

    return env_file


@pytest.fixture
def mock_gmail_secret(temp_dir):
    """Create a mock Gmail OAuth secret file."""
    secret_file = temp_dir / "client_secret_test.json"
    secret_data = {
        "web": {
            "client_id": "test123.apps.googleusercontent.com",
            "client_secret": "test_secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    with open(secret_file, "w") as f:
        json.dump(secret_data, f)
    return secret_file


@pytest.fixture
def sample_tracks():
    """Sample Spotify track IDs."""
    return ["spotify:track:track1", "spotify:track:track2", "spotify:track:track3"]


@pytest.fixture
def sample_playlist():
    """Sample Spotify playlist response."""
    return {
        "id": "test_playlist_id_123",
        "name": "Playlist 2026-02-05",
        "description": "",
        "tracks": {"total": 0},
    }
