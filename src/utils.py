"""Shared utility functions."""

import re


def is_valid_spotify_id(spotify_id: str) -> bool:
    """Validate that a Spotify ID is 22 alphanumeric characters."""
    if not spotify_id or not isinstance(spotify_id, str):
        return False
    return bool(re.match(r"^[A-Za-z0-9]{22}$", spotify_id))
