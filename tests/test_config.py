"""
Tests for configuration module.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import (
    AnthropicConfig,
    AppConfig,
    ConfigurationError,
    DatabaseConfig,
    EmailConfig,
    GmailConfig,
    SpotifyConfig,
    load_config,
)


class TestSpotifyConfig:
    """Tests for Spotify configuration."""

    def test_valid_config(self, mock_env_file):
        """Test that valid configuration loads successfully."""
        config = SpotifyConfig()
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert "playlist-modify" in config.scopes

    def test_missing_client_id(self, monkeypatch):
        """Test error when client_id is missing."""
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_secret")
        monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            SpotifyConfig()

        assert "client_id" in str(exc_info.value)

    def test_placeholder_value_rejected(self, monkeypatch):
        """Test that placeholder values are rejected."""
        monkeypatch.setenv("SPOTIFY_CLIENT_ID", "your_spotify_client_id_here")
        monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "test_secret")

        with pytest.raises(ValidationError) as exc_info:
            SpotifyConfig()

        assert "not configured" in str(exc_info.value)


class TestAnthropicConfig:
    """Tests for Anthropic configuration."""

    def test_valid_config(self, mock_env_file):
        """Test that valid configuration loads successfully."""
        config = AnthropicConfig()
        assert config.api_key == "test_api_key_12345"
        assert config.model_name == "claude-haiku-4-5-20251001"
        assert config.max_retries == 3

    def test_missing_api_key(self, monkeypatch):
        """Test error when API key is missing."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValidationError) as exc_info:
            AnthropicConfig()

        assert "api_key" in str(exc_info.value)


class TestGmailConfig:
    """Tests for Gmail configuration."""

    def test_valid_config(self, mock_env_file, mock_gmail_secret):
        """Test that valid configuration loads successfully."""
        config = GmailConfig()
        assert config.secret_path.exists()
        assert "gmail.readonly" in config.scopes

    def test_missing_secret_file(self, monkeypatch):
        """Test error when secret file doesn't exist."""
        monkeypatch.setenv("GMAIL_SECRET_PATH", "nonexistent_file.json")

        with pytest.raises(ValidationError) as exc_info:
            GmailConfig()

        assert "not found" in str(exc_info.value)


class TestDatabaseConfig:
    """Tests for Database configuration."""

    def test_default_path(self):
        """Test default database path."""
        config = DatabaseConfig()
        assert config.path == Path("playlists.db")

    def test_custom_path(self, monkeypatch):
        """Test custom database path."""
        monkeypatch.setenv("DATABASE_PATH", "custom.db")
        config = DatabaseConfig()
        assert config.path == Path("custom.db")


class TestEmailConfig:
    """Tests for Email configuration."""

    def test_creates_directory(self, temp_dir, monkeypatch):
        """Test that email directory is created if it doesn't exist."""
        email_dir = temp_dir / "emails"
        assert not email_dir.exists()

        monkeypatch.setenv("EMAIL_PATH", str(email_dir))
        config = EmailConfig()

        assert config.path.exists()
        assert config.path.is_dir()

    def test_default_max_emails(self):
        """Test default max emails per run."""
        config = EmailConfig()
        assert config.max_emails_per_run == 10


class TestAppConfig:
    """Tests for main AppConfig."""

    def test_valid_config(self, mock_env_file, mock_gmail_secret):
        """Test that valid configuration loads all sections."""
        config = AppConfig()

        assert config.is_valid()
        assert config.spotify is not None
        assert config.anthropic is not None
        assert config.gmail is not None
        assert config.database is not None
        assert config.email is not None

    def test_invalid_config_collects_errors(self, monkeypatch):
        """Test that invalid config collects all errors."""
        monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ConfigurationError):
            AppConfig(validate=True)

    def test_no_validation_on_request(self, monkeypatch):
        """Test that validation can be skipped."""
        monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)

        config = AppConfig(validate=False)
        assert not config.is_valid()
        assert len(config.errors) > 0

    def test_validate_for_email_download(self, mock_env_file, mock_gmail_secret):
        """Test validation for email download task."""
        config = AppConfig()
        assert config.validate_for_email_download()

    def test_validate_for_playlist_creation(self, mock_env_file, mock_gmail_secret):
        """Test validation for playlist creation task."""
        config = AppConfig()
        assert config.validate_for_playlist_creation()


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, mock_env_file, mock_gmail_secret):
        """Test loading valid configuration."""
        config = load_config()
        assert config.is_valid()

    def test_load_invalid_config_raises(self, monkeypatch):
        """Test that invalid config raises error."""
        monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)

        with pytest.raises(ConfigurationError):
            load_config(validate=True)
