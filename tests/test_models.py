"""
Tests for Pydantic data models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.classes import album, boom_email, extract_release, playlist, track


class TestBoomEmail:
    """Tests for boom_email model."""

    def test_valid_email(self):
        """Test creating valid email object."""
        email = boom_email(date=datetime(2026, 2, 5, 10, 0, 0), body="Test email body")
        assert email.date.year == 2026
        assert email.body == "Test email body"

    def test_string_date_parsing(self):
        """Test that string dates are parsed correctly."""
        email = boom_email(date="2026-02-05T10:00:00", body="Test body")
        assert isinstance(email.date, datetime)
        assert email.date.year == 2026

    def test_missing_body_fails(self):
        """Test that missing body field raises error."""
        with pytest.raises(ValidationError):
            boom_email(date=datetime.now())


class TestAlbum:
    """Tests for album model."""

    def test_valid_album(self):
        """Test creating valid album object."""
        test_album = album(
            artists=["Aphex Twin"],
            title="Selected Ambient Works",
            id="spotify:album:123",
        )
        assert test_album.artists == ["Aphex Twin"]
        assert test_album.title == "Selected Ambient Works"

    def test_multiple_artists(self):
        """Test album with multiple artists."""
        test_album = album(
            artists=["Artist 1", "Artist 2", "Artist 3"],
            title="Collaboration Album",
            id="spotify:album:456",
        )
        assert len(test_album.artists) == 3

    def test_missing_id_fails(self):
        """Test that missing id raises error."""
        with pytest.raises(ValidationError):
            album(artists=["Test"], title="Test Album")


class TestExtractRelease:
    """Tests for extract_release model."""

    def test_valid_release(self):
        """Test creating valid extract_release object."""
        release = extract_release(artist=["Four Tet"], album="Three")
        assert release.artist == ["Four Tet"]
        assert release.album == "Three"

    def test_multiple_artists(self):
        """Test release with multiple artists."""
        release = extract_release(artist=["Artist A", "Artist B"], album="Joint Album")
        assert len(release.artist) == 2

    def test_empty_artist_list(self):
        """Test that empty artist list is allowed."""
        release = extract_release(artist=[], album="Unknown Artist Album")
        assert release.artist == []


class TestPlaylist:
    """Tests for playlist model."""

    def test_valid_playlist(self):
        """Test creating valid playlist object."""
        test_albums = [
            album(artists=["Artist 1"], title="Album 1", id="id1"),
            album(artists=["Artist 2"], title="Album 2", id="id2"),
        ]

        test_playlist = playlist(releases=test_albums, title="Test Playlist")

        assert test_playlist.title == "Test Playlist"
        assert len(test_playlist.releases) == 2

    def test_empty_releases(self):
        """Test playlist with no releases."""
        test_playlist = playlist(releases=[], title="Empty Playlist")
        assert len(test_playlist.releases) == 0


class TestTrack:
    """Tests for track model."""

    def test_valid_track(self):
        """Test creating valid track object."""
        test_track = track(artist="Test Artist", album="Test Album", track_id="spotify:track:abc123")
        assert test_track.artist == "Test Artist"
        assert test_track.album == "Test Album"
        assert test_track.track_id == "spotify:track:abc123"

    def test_missing_track_id_fails(self):
        """Test that missing track_id raises error."""
        with pytest.raises(ValidationError):
            track(artist="Test", album="Test Album")


class TestModelSerialization:
    """Tests for model serialization/deserialization."""

    def test_album_to_dict(self):
        """Test converting album to dictionary."""
        test_album = album(artists=["Test Artist"], title="Test Album", id="test_id")

        album_dict = test_album.model_dump()
        assert album_dict["artists"] == ["Test Artist"]
        assert album_dict["title"] == "Test Album"

    def test_album_to_json(self):
        """Test converting album to JSON string."""
        test_album = album(artists=["Test Artist"], title="Test Album", id="test_id")

        json_str = test_album.model_dump_json()
        assert "Test Artist" in json_str
        assert "Test Album" in json_str

    def test_album_from_dict(self):
        """Test creating album from dictionary."""
        album_dict = {
            "artists": ["Test Artist"],
            "title": "Test Album",
            "id": "test_id",
        }

        test_album = album(**album_dict)
        assert test_album.artists == ["Test Artist"]
