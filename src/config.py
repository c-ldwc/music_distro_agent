"""
Configuration validation and management module.

Provides centralized configuration with validation, defaults,
and helpful error messages for missing or invalid settings.
"""

import sys
from pathlib import Path

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpotifyConfig(BaseSettings):
    """Spotify API configuration settings."""

    client_id: str = Field(..., description="Spotify application client ID")
    client_secret: str = Field(..., description="Spotify application client secret")
    scopes: str = Field(
        default="playlist-modify-public,playlist-modify-private,playlist-read-private",
        description="Comma-separated list of Spotify API scopes",
    )
    redirect_uri: str = Field(default="http://localhost:8888/callback", description="OAuth redirect URI")

    model_config = SettingsConfigDict(
        env_prefix="SPOTIFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("client_id", "client_secret")
    @classmethod
    def validate_not_placeholder(cls, v: str, info) -> str:
        """Ensure credentials are not placeholder values."""
        if not v or v.startswith("your_") or v == "":
            raise ValueError(
                f"{info.field_name} is not configured. Please set SPOTIFY_{info.field_name.upper()} in your .env file"
            )
        return v


class AnthropicConfig(BaseSettings):
    """Anthropic/Claude AI API configuration settings."""

    api_key: str = Field(..., description="Anthropic API key for Claude")
    model_name: str = Field(default="claude-haiku-4-5-20251001", description="Claude model to use")
    max_retries: int = Field(default=3, description="Maximum number of retries for API calls")

    model_config = SettingsConfigDict(
        env_prefix="ANTHROPIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("api_key")
    @classmethod
    def validate_not_placeholder(cls, v: str) -> str:
        """Ensure API key is not placeholder value."""
        if not v or v.startswith("your_") or v == "sk-ant-api03-...":
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured. Please set it in your .env file with a valid API key"
            )
        return v


class GmailConfig(BaseSettings):
    """Gmail API configuration settings."""

    secret_path: Path = Field(..., description="Path to Google OAuth client secret JSON file")
    scopes: str = Field(
        default="https://www.googleapis.com/auth/gmail.readonly",
        description="Gmail API scopes",
        env_parse=lambda x: x.split(","),
    )
    token_path: Path = Field(default=Path("token.json"), description="Path to store OAuth tokens")

    model_config = SettingsConfigDict(env_prefix="GMAIL_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("secret_path")
    @classmethod
    def validate_secret_exists(cls, v: Path) -> Path:
        """Ensure the secret file exists."""
        if not v.exists():
            raise ValueError(
                f"Gmail secret file not found at {v}. "
                f"Please download OAuth credentials from Google Cloud Console "
                f"and set GMAIL_SECRET_PATH in .env"
            )
        return v


class DatabaseConfig(BaseSettings):
    """Database configuration settings."""

    path: Path = Field(default=Path("playlists.db"), description="Path to SQLite database file")

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class EmailConfig(BaseSettings):
    """Email processing configuration settings."""

    path: Path = Field(
        default=Path("sources"),
        description="Directory for storing downloaded emails",
    )
    max_emails_per_run: int = Field(default=10, description="Maximum number of emails to process in one run")

    model_config = SettingsConfigDict(env_prefix="EMAIL_", env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("path")
    @classmethod
    def create_if_not_exists(cls, v: Path) -> Path:
        """Create email directory if it doesn't exist."""
        v.mkdir(exist_ok=True, parents=True)
        return v


class AppConfig:
    """
    Main application configuration aggregating all sub-configurations.

    This class validates all configuration on initialization and provides
    helpful error messages for missing or invalid settings.
    """

    def __init__(self, validate: bool = True):
        """
        Initialize application configuration.

        Args:
            validate: Whether to validate configuration on init (default: True)
        """
        self.errors = []

        try:
            self.spotify = SpotifyConfig()
        except ValidationError as e:
            self.errors.append(("Spotify Configuration", e))
            self.spotify = None

        try:
            self.anthropic = AnthropicConfig()
        except ValidationError as e:
            self.errors.append(("Anthropic Configuration", e))
            self.anthropic = None

        try:
            self.gmail = GmailConfig()
        except ValidationError as e:
            self.errors.append(("Gmail Configuration", e))
            self.gmail = None

        try:
            self.database = DatabaseConfig()
        except ValidationError as e:
            self.errors.append(("Database Configuration", e))
            self.database = None

        try:
            self.email = EmailConfig()
        except ValidationError as e:
            self.errors.append(("Email Configuration", e))
            self.email = None

        if validate and self.errors:
            self._print_errors()
            raise ConfigurationError("Configuration validation failed")

    def _print_errors(self):
        """Print all configuration errors in a user-friendly format."""
        print("\n" + "=" * 70)
        print("❌ CONFIGURATION ERRORS DETECTED")
        print("=" * 70)

        for section, error in self.errors:
            print(f"\n📋 {section}:")
            for err in error.errors():
                field = err["loc"][0] if err["loc"] else "unknown"
                message = err["msg"]
                print(f"  • {field}: {message}")

        print("\n" + "=" * 70)
        print("💡 Quick Fix:")
        print("  1. Copy .env.example to .env: cp .env.example .env")
        print("  2. Edit .env and fill in your actual credentials")
        print("  3. Ensure all required files exist (Gmail secret, etc.)")
        print("=" * 70 + "\n")

    def is_valid(self) -> bool:
        """Check if configuration is valid."""
        return len(self.errors) == 0

    def validate_for_email_download(self) -> bool:
        """Validate configuration needed for email download."""
        if not self.gmail:
            print("❌ Gmail configuration is required for email download")
            return False
        if not self.email:
            print("❌ Email configuration is required")
            return False
        return True

    def validate_for_playlist_creation(self) -> bool:
        """Validate configuration needed for playlist creation."""
        if not self.spotify:
            print("❌ Spotify configuration is required for playlist creation")
            return False
        if not self.anthropic:
            print("❌ Anthropic configuration is required for AI processing")
            return False
        if not self.database:
            print("❌ Database configuration is required")
            return False
        if not self.email:
            print("❌ Email configuration is required")
            return False
        return True


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""

    pass


def load_config(validate: bool = True) -> AppConfig:
    """
    Load and validate application configuration.

    Args:
        validate: Whether to validate and exit on errors (default: True)

    Returns:
        AppConfig instance

    Raises:
        ConfigurationError: If validation fails and validate=True
    """
    return AppConfig(validate=validate)


# Convenience function for backward compatibility
def get_validated_config() -> AppConfig:
    """
    Get validated configuration or exit with helpful error messages.

    Returns:
        Valid AppConfig instance
    """
    try:
        return load_config(validate=True)
    except ConfigurationError:
        sys.exit(1)
