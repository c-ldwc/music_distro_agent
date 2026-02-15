"""
Unified CLI for Spotify Playlist Automation.

Provides commands for:
- process: Process emails and create playlists
- sync: Sync playlists from database to Spotify
- download: Download new emails from Gmail
"""

import sys

import click
from httpx import HTTPStatusError
from langchain.tools import tool

from src.agent import ExtractionAgent, SearchAgent
from src.config import load_config
from src.db import get_db_connection
from src.email_utils import gmail, gmail_auth_context
from src.logging_config import get_logger, setup_logging
from src.services import EmailProcessor, SpotifyService


@click.group()
@click.version_option(version="0.1.0", prog_name="spotify-automation")
def cli():
    """Spotify Playlist Automation CLI

    Automates creating Spotify playlists from music distributor emails
    using AI extraction and matching.
    """
    pass


@cli.command()
@click.option('--limit', default=10, type=int, help='Maximum number of emails to process')
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
def process(limit: int, log_level: str):
    """Process emails and create Spotify playlists.

    Reads emails from the configured directory, extracts music releases
    using AI, searches Spotify for matches, and creates/updates playlists.
    """
    # Setup logging
    logger = setup_logging(log_level=log_level)
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
        """Search Spotify for an album by artist."""
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
        'extract': ExtractionAgent(
            api_key=config.anthropic.api_key,
            temperature=0.0
        ),
        'search': SearchAgent(
            api_key=config.anthropic.api_key,
            temperature=0.0
        )
    }

    # Connect to database
    module_logger.info("Connecting to database...")
    try:
        db_conn = get_db_connection()
        module_logger.info("✓ Database connection established")
    except Exception as e:
        module_logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    # Process emails
    processor = EmailProcessor(config, spotify_service, agents, db_conn, module_logger)
    stats = processor.process_all_emails(search_tool=search, limit=limit)

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


@cli.command()
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
def sync(log_level: str):
    """Sync playlists from database to Spotify.

    Reads playlists from the database and adds tracks to empty
    playlists on Spotify.
    """
    from collections import defaultdict

    # Setup logging
    setup_logging(log_level=log_level)
    logger = get_logger(__name__)

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Connect to database
    logger.info("Connecting to database...")
    db_conn = get_db_connection()

    # Get playlists from database
    logger.info("Reading playlists from database...")
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT playlist_id, playlist_name, id
        FROM playlists
        WHERE id IS NOT NULL
        ORDER BY playlist_name
    """)

    playlists = defaultdict(lambda: {"name": "", "tracks": []})
    for row in cursor.fetchall():
        playlist_id, playlist_name, track_id = row
        if not playlists[playlist_id]["name"]:
            playlists[playlist_id]["name"] = playlist_name
        playlists[playlist_id]["tracks"].append(track_id)

    logger.info(f"Found {len(playlists)} playlists in database")

    # Setup Spotify client
    logger.info("Setting up Spotify connection...")
    spotify_service = SpotifyService(config.spotify)
    spotify_service.authenticate()
    spot_client = spotify_service.client
    logger.info("✅ Connected to Spotify")

    # Check each playlist
    logger.info("Checking playlists...")
    synced_count = 0
    skipped_count = 0

    for playlist_id, playlist_data in playlists.items():
        playlist_name = playlist_data["name"]
        tracks = playlist_data["tracks"]

        logger.info(f"📋 Checking: {playlist_name} ({playlist_id})")
        logger.info(f"   Database has {len(tracks)} tracks")

        # Check if playlist exists on Spotify
        if not spot_client.playlist_exist(playlist_id):
            logger.warning("   ⚠️  Playlist does not exist on Spotify - skipping")
            skipped_count += 1
            continue

        # Check if playlist has tracks
        try:
            result = spot_client._construct_call(f"playlists/{playlist_id}")
            track_count = result["tracks"]["total"]
        except Exception as e:
            logger.error(f"   ❌ Error checking playlist: {e}")
            skipped_count += 1
            continue

        if track_count > 0:
            logger.info(f"   ℹ️  Playlist already has {track_count} tracks - skipping")
            skipped_count += 1
            continue

        # Playlist exists but is empty - add tracks
        logger.info(f"   ✨ Playlist is empty - adding {len(tracks)} tracks...")
        try:
            spot_client.add_to_playlist(tracks=tracks, playlist_id=playlist_id)
            logger.info(f"   ✅ Successfully added {len(tracks)} tracks")
            synced_count += 1
        except Exception as e:
            logger.error(f"   ❌ Error adding tracks: {e}")
            skipped_count += 1

    # Close database connection
    db_conn.close()

    # Summary
    logger.info("=" * 50)
    logger.info("Sync complete!")
    logger.info(f"  Synced: {synced_count} playlists")
    logger.info(f"  Skipped: {skipped_count} playlists")
    logger.info("=" * 50)


@cli.command()
@click.option('--log-level', default='INFO', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']),
              help='Logging level')
def download(log_level: str):
    """Download new emails from Gmail.

    Authenticates with Gmail and fetches unread emails,
    saving them to the configured email directory.
    """
    # Setup logging
    setup_logging(log_level=log_level)
    logger = get_logger(__name__)

    logger.info("Starting email download process...")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Create gmail auth context
    gmail_context = gmail_auth_context(
        token=str(config.gmail.token_path),
        secret=str(config.gmail.secret_path),
        scopes=[config.gmail.scopes],
    )

    # Initialize gmail client
    gmail_client = gmail(
        email_dir=config.email.path,
        gmail_context=gmail_context,
    )

    # Authenticate with Gmail
    logger.info("Authenticating with Gmail...")
    try:
        gmail_client.auth()
        logger.info("✓ Authentication successful")
    except Exception as e:
        logger.error(f"Gmail authentication failed: {e}")
        sys.exit(1)

    # Fetch new emails
    logger.info("Fetching new emails...")
    try:
        gmail_client.fetch_new_emails()
        logger.info("✓ Email download complete")
    except Exception as e:
        logger.error(f"Failed to download emails: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
