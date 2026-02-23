"""Spotify service wrapper for authentication and client management."""

from src.config import SpotifyConfig
from src.spotify import auth_params, spotify


class SpotifyService:
    """Wrapper for Spotify client with authentication."""

    def __init__(self, config: SpotifyConfig):
        """
        Initialize Spotify service.

        Args:
            config: Spotify configuration with credentials
        """
        self.config = config
        self.client = None

    def authenticate(self):
        """
        Initialize and authenticate Spotify client.

        Returns:
            Authenticated Spotify client
        """
        auth = auth_params(
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            scope=self.config.scopes,
            redirect_uri=self.config.redirect_uri,
            state="state",
        )
        self.client = spotify(auth_params=auth)
        self.client.get_auth_code_and_tokens()
        return self.client
