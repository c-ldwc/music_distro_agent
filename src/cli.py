"""
Unified CLI for Spotify Playlist Automation.

Provides commands for:
- process: Process emails and create playlists
- sync: Sync playlists from database to Spotify
- download: Download new emails from Gmail
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from numpy import argsort

import click
import httpx
from bs4 import BeautifulSoup
from httpx import HTTPStatusError
from langchain.tools import tool

from src import spotify
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
@click.option("--limit", default=None, type=int, help="Maximum number of emails to process (default from config)")
@click.option(
    "--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Logging level"
)
@click.option("--path", default="boomkat_emails", type=str)
def process(limit: int | None, log_level: str, path=str | None):
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

    if limit is None:
        limit = config.email.max_emails_per_run

    if path:
        config.email.path = Path(path)

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
@click.option("--top-n", "-n", default=5, type=click.INT)
def get_popular(top_n: int):
    """Get top N most popular tracks from each album and create a new playlist.

    Creates a new playlist named '{original_name}: Top' containing the most
    popular tracks from each album in the original playlist. Tracks are stored
    in the database and can be synced later using 'sync' command.
    """
    from src.classes import track
    from src.db import record_track

    logger = setup_logging()
    config = load_config()
    logger.info(f"Connecting to db {config.database.path}")
    db_conn = get_db_connection(str(config.database.path))
    logger.info("Connecting to spotify")
    spotify_service = SpotifyService(config.spotify)
    spotify_service.authenticate()

    logger.info("Getting playlist tracks")
    cursor = db_conn.cursor()

    playlists = cursor.execute("select distinct playlist_id, playlist_name from playlists").fetchall()
    logger.info(f"Found {len(playlists)} playlists to process")

    for playlist_id, playlist_name in playlists:
        new_name = playlist_name + ": Top"
        logger.info(f"Processing tracks for {playlist_name}, {playlist_id}")

        # Check if the new playlist already exists
        existing_playlist = spotify_service.client.get_playlist_by_name(new_name)

        if existing_playlist:
            new_playlist_id = existing_playlist["id"]
            logger.info(f"✓ Playlist '{new_name}' already exists with ID: {new_playlist_id}")
        else:
            # Create new playlist
            logger.info(f"Creating new playlist: {new_name}")
            new_playlist = spotify_service.client.create_playlist(name=new_name, public=True)
            new_playlist_id = new_playlist["id"]
            logger.info(f"✓ Created playlist with ID: {new_playlist_id}")

        albums = cursor.execute(
            "select distinct artist, album from playlists where playlist_id =?", (playlist_id,)
        ).fetchall()

        logger.info(f"Processing {len(albums)} albums")
        all_top_tracks = []

        for artist, album in albums:
            logger.info(f"  Processing {artist}: {album}")
            ids = cursor.execute(
                """
                SELECT distinct id
                FROM playlists
                where artist = ? and album = ?""",
                (artist, album),
            ).fetchall()

            track_ids = []
            for row in ids:
                track_ids.append(row[0])

            if not track_ids:
                logger.warning(f"  No tracks found for {artist}: {album}")
                continue

            logger.info(f"  Found {len(track_ids)} tracks")
            ids_str = ",".join(track_ids)

            try:
                tracks = spotify_service.client.get_tracks(ids=ids_str)

                # Sort by popularity (descending) and get top N
                popularity = [t["popularity"] for t in tracks]
                # argsort gives ascending order, so reverse to get highest first
                idx = argsort(popularity)[::-1][:top_n]

                # Record each top track in database
                for i in idx:
                    track_info = tracks[i]
                    track_obj = track(
                        artist=artist,
                        album=album,
                        track_id=track_info["id"]
                    )
                    record_track(db_conn, track_obj, new_name, new_playlist_id)
                    all_top_tracks.append(track_info["id"])
                    logger.debug(f"    ✓ Recorded: {track_info['name']} (popularity: {track_info['popularity']})")

                logger.info(f"  ✓ Recorded top {len(idx)} tracks from {album}")

            except Exception as e:
                logger.error(f"  ✗ Error processing tracks for {artist}: {album} - {e}")
                continue

        logger.info(f"✅ Completed playlist '{new_name}': {len(all_top_tracks)} total tracks recorded")
        logger.info(f"   Use 'spotify-automation sync' to add tracks to Spotify")

    # Cleanup
    db_conn.close()
    logger.info("=" * 60)
    logger.info("All playlists processed successfully!")
    logger.info("=" * 60)


@cli.command()
@click.option(
    "--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Logging level"
)
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
    db_conn = get_db_connection(str(config.database.path))

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
@click.option(
    "--log-level", default="INFO", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]), help="Logging level"
)
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


@cli.command()
@click.option("--url", type=str, required=True)
@click.option("--output", "-o", type=str, default=None)
@click.option("--body", "-b", is_flag=True, help="Extract only the <body> element")
@click.option("--script", "-s", is_flag=True, help="Keep <script> and <noscript> tags (only applies with --body)")
@click.option("--date", "-d", type=str, default=None, help="Email date in ISO format (defaults to now)")
@click.option(
    "--playlist-name",
    "-p",
    type=str,
    default=None,
    help="Playlist name to associate with this email (defaults to 'Boomkat <date>')",
)
def scrape(url: str, output: str | None, body: bool, script: bool, date: str | None, playlist_name: str | None):
    """Scrape a URL and save it as a boom_email JSON file."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
    }
    try:
        response = httpx.get(url=url, headers=headers)
        response.raise_for_status()
    except HTTPStatusError:
        from curl_cffi import requests

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
        }

        # Use curl_cffi to impersonate a real browser
        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome120",  # Mimics Chrome's TLS fingerprint
            # follow_redirects=True  # Requests API uses 'allow_redirects'
        )
    if not output:
        # Use scraped_url as the default and do not overwrite
        i = len([i for i in os.listdir(".") if re.match("scraped_url", i) is not None])
        output = f"scraped_url{i}.txt"
    if body:
        soup = BeautifulSoup(response.text, "html.parser").find("body")
        if not script:
            for sc in soup.find_all("script"):
                sc.decompose()
            for nsc in soup.find_all("noscript"):
                nsc.decompose()
        text = soup.get_text(separator="\n", strip=True)
    else:
        text = response.content.decode()

    email_date = date if date else datetime.now().isoformat()
    payload: dict = {"date": email_date, "body": text}
    if playlist_name:
        payload["playlist_name"] = playlist_name
    with open(output, "w") as f:
        json.dump(payload, f, indent=2)


if __name__ == "__main__":
    cli()
