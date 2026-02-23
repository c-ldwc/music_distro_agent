"""
Spotify Playlist Automation - Main Entry Point

Processes music distributor emails to automatically create Spotify playlists.
Extracts releases using AI, searches Spotify for matches, and maintains a database.
"""

import sys

from httpx import HTTPStatusError
from langchain.tools import tool

from src.agent import ExtractionAgent, SearchAgent
from src.config import load_config
from src.db import get_db_connection
from src.logging_config import get_logger, setup_logging
from src.services import EmailProcessor, SpotifyService


def main():
    """Main entry point for playlist automation."""
    # Setup logging
    logger = setup_logging(log_level="INFO")
    module_logger = get_logger(__name__)

    module_logger.info("Starting Spotify playlist automation...")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.error("Please ensure .env file is configured correctly")
        sys.exit(1)

    # Initialize and authenticate Spotify
    module_logger.info("Initializing Spotify client...")
    spotify_service = SpotifyService(config.spotify)

    try:
        spotify_service.authenticate()
        module_logger.info("✓ Spotify authentication successful")
    except Exception as e:
        module_logger.error(f"Spotify authentication failed: {e}")
        sys.exit(1)

    # Define search tool for agents
    @tool
    def search(artist: str, album: str):
        """
        Search Spotify for an album by artist.

        Args:
            artist: The name of the artist to search for
            album: The name of the album to search for

        Returns:
            List of JSON strings with search results containing artist, title, and id fields
        """
        module_logger.debug(f"Searching for artist: {artist}, album: {album}")
        try:
            results = spotify_service.client.search(artist, album)
            return [i.model_dump_json() for i in results]
        except HTTPStatusError as err:
            module_logger.error(f"Spotify API error during search: {err.response.status_code} - {err}")
            return []
        except Exception as err:
            module_logger.error(f"Unexpected error in search: {err}", exc_info=True)
            return []

    # Initialize AI agents
    module_logger.info("Initializing AI agents...")
    agents = {
        "extract": ExtractionAgent(
            api_key=config.anthropic.api_key,
            model_name=config.anthropic.model_name,
            max_retries=config.anthropic.max_retries,
            temperature=0.0,
        ),
        "search": SearchAgent(
            api_key=config.anthropic.api_key,
            model_name=config.anthropic.model_name,
            max_retries=config.anthropic.max_retries,
            temperature=0.0,
        ),
    }

    # Connect to database
    module_logger.info("Connecting to database...")
    try:
        db_conn = get_db_connection(str(config.database.path))
        module_logger.info("✓ Database connection established")
    except Exception as e:
        module_logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    # Process emails
    processor = EmailProcessor(config, spotify_service, agents, db_conn, module_logger)
    stats = processor.process_all_emails(search_tool=search, limit=config.email.max_emails_per_run)

    # Print summary
    module_logger.info("=" * 60)
    module_logger.info("Processing complete!")
    module_logger.info(f"Total emails processed: {stats['processed']}")
    module_logger.info(f"Successful: {stats['success']}")
    module_logger.info(f"Errors: {stats['errors']}")
    module_logger.info(f"Total albums found: {stats['total_albums_found']}")
    module_logger.info(f"Total albums not found: {stats['total_albums_not_found']}")
    module_logger.info("=" * 60)

    # Cleanup
    if db_conn:
        db_conn.close()
        module_logger.debug("Database connection closed")


if __name__ == "__main__":
    main()
