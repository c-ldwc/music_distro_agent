"""
Unified CLI for Spotify Playlist Automation.

Consolidates email download, processing, and playlist management into a single interface.
"""

import sys
from collections import defaultdict

import click
from httpx import HTTPStatusError
from langchain.tools import tool

from src.agent import ExtractionAgent, SearchAgent
from src.config import load_config
from src.db import get_db_connection
from src.email_utils import gmail, gmail_auth_context
from src.logging_config import get_logger, setup_logging
from src.services import EmailProcessor, SpotifyService
from src.spotify import auth_params, spotify


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """
    Spotify Playlist Automation CLI.

    Automatically create and sync Spotify playlists from Boomkat music distributor emails
    using AI-powered extraction and search.
    """
    pass


@cli.command()
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level",
)
def download(log_level):
    """
    Download new emails from Gmail.

    Authenticates with Gmail API and fetches unread Boomkat emails,
    saving them to the configured email directory.
    """
    setup_logging(log_level=log_level)
    click.echo("Starting email download process...")

    try:
        config = load_config()
    except Exception as e:
        click.secho(f"❌ Configuration error: {e}", fg="red", err=True)
        sys.exit(1)

    # Validate configuration
    if not config.validate_for_email_download():
        sys.exit(1)

    try:
        # Create Gmail auth context
        gmail_context = gmail_auth_context(
            token=str(config.gmail.token_path),
            secret=str(config.gmail.secret_path),
            scopes=[config.gmail.scopes],
        )

        # Initialize Gmail client
        gmail_client = gmail(
            email_dir=config.email.path,
            gmail_context=gmail_context,
        )

        # Authenticate and fetch
        click.echo("Authenticating with Gmail...")
        gmail_client.auth()
        click.secho("✓ Authentication successful", fg="green")

        click.echo("Fetching new emails...")
        gmail_client.fetch_new_emails()
        click.secho("✓ Email download complete", fg="green")

    except Exception as e:
        click.secho(f"❌ Error: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--limit",
    type=int,
    default=10,
    help="Maximum number of emails to process",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level",
)
def process(limit, log_level):
    """
    Process emails and create Spotify playlists.

    Main workflow: reads emails, extracts releases using AI, searches Spotify,
    creates dated playlists, and records all actions in the database.
    """
    logger = setup_logging(log_level=log_level)
    module_logger = get_logger(__name__)

    click.echo("Starting Spotify playlist automation...")

    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        click.secho(f"❌ Configuration error: {e}", fg="red", err=True)
        sys.exit(1)

    # Validate configuration
    if not config.validate_for_playlist_creation():
        sys.exit(1)

    # Initialize and authenticate Spotify
    click.echo("Initializing Spotify client...")
    spotify_service = SpotifyService(config.spotify)

    try:
        spotify_service.authenticate()
        click.secho("✓ Spotify authentication successful", fg="green")
    except Exception as e:
        click.secho(f"❌ Spotify authentication failed: {e}", fg="red", err=True)
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
    click.echo("Initializing AI agents...")
    agents = {
        "extract": ExtractionAgent(api_key=config.anthropic.api_key, temperature=0.0),
        "search": SearchAgent(api_key=config.anthropic.api_key, temperature=0.0),
    }

    # Connect to database
    click.echo("Connecting to database...")
    try:
        db_conn = get_db_connection()
        click.secho("✓ Database connection established", fg="green")
    except Exception as e:
        click.secho(f"❌ Failed to connect to database: {e}", fg="red", err=True)
        sys.exit(1)

    # Process emails
    processor = EmailProcessor(config, spotify_service, agents, db_conn, module_logger)
    stats = processor.process_all_emails(search_tool=search, limit=limit)

    # Print summary
    click.echo("\n" + "=" * 60)
    click.secho("Processing complete!", fg="green", bold=True)
    click.echo(f"Total emails processed: {stats['processed']}")
    click.echo(f"Successful: {stats['success']}")
    click.echo(f"Errors: {stats['errors']}")
    click.echo(f"Total albums found: {stats['total_albums_found']}")
    click.echo(f"Total albums not found: {stats['total_albums_not_found']}")
    click.echo("=" * 60)

    # Cleanup
    if db_conn:
        db_conn.close()


@cli.command()
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level",
)
def sync(log_level):
    """
    Sync playlists from database to Spotify.

    Checks all playlists in the database, identifies empty playlists on Spotify,
    and adds tracks from the database to those playlists.
    """
    setup_logging(log_level=log_level)

    # Connect to database
    click.echo("Connecting to database...")
    db_conn = get_db_connection()

    # Get playlists from database
    click.echo("Reading playlists from database...")
    db_playlists = _get_playlist_tracks_from_db(db_conn)
    click.echo(f"Found {len(db_playlists)} playlists in database")

    # Setup Spotify client
    click.echo("\nSetting up Spotify connection...")
    try:
        config = load_config()
    except Exception as e:
        click.secho(f"❌ Configuration error: {e}", fg="red", err=True)
        sys.exit(1)

    auth_params_obj = auth_params(
        client_id=config.spotify.client_id,
        client_secret=config.spotify.client_secret,
        scope=config.spotify.scopes,
        state="state",
    )

    spot_client = spotify(auth_params=auth_params_obj)
    spot_client.get_auth_code_and_tokens()
    click.secho("✓ Connected to Spotify", fg="green")

    # Check each playlist
    click.echo("\nChecking playlists...")
    synced_count = 0
    skipped_count = 0

    for playlist_id, playlist_data in db_playlists.items():
        playlist_name = playlist_data["name"]
        tracks = playlist_data["tracks"]

        click.echo(f"\n📋 Checking: {playlist_name} ({playlist_id})")
        click.echo(f"   Database has {len(tracks)} tracks")

        # Check if playlist exists on Spotify
        if not spot_client.playlist_exist(playlist_id):
            click.secho("   ⚠️  Playlist does not exist on Spotify - skipping", fg="yellow")
            skipped_count += 1
            continue

        # Check if playlist has tracks
        track_count = _get_spotify_playlist_track_count(spot_client, playlist_id)

        if track_count < 0:
            click.secho("   ❌ Error checking playlist - skipping", fg="red")
            skipped_count += 1
            continue

        if track_count > 0:
            click.echo(f"   ℹ️  Playlist already has {track_count} tracks - skipping")
            skipped_count += 1
            continue

        # Playlist exists but is empty - add tracks
        click.echo(f"   ✨ Playlist is empty - adding {len(tracks)} tracks...")
        try:
            spot_client.add_to_playlist(tracks=tracks, playlist_id=playlist_id)
            click.secho(f"   ✓ Successfully added {len(tracks)} tracks", fg="green")
            synced_count += 1
        except Exception as e:
            click.secho(f"   ❌ Error adding tracks: {e}", fg="red")
            skipped_count += 1

    # Close database connection
    db_conn.close()

    # Summary
    click.echo("\n" + "=" * 50)
    click.secho("Sync complete!", fg="green", bold=True)
    click.echo(f"  Synced: {synced_count} playlists")
    click.echo(f"  Skipped: {skipped_count} playlists")
    click.echo("=" * 50)


@cli.command()
@click.option(
    "--id",
    "playlist_id",
    required=True,
    help="Spotify playlist ID to sync",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Set logging level",
)
def create(playlist_id, log_level):
    """
    Create or update a specific playlist by ID.

    Reads tracks for the specified playlist from the database and adds them to Spotify.
    """
    setup_logging(log_level=log_level)

    click.echo(f"Creating/updating playlist: {playlist_id}")

    # Connect to database
    conn = get_db_connection()

    # Get tracks for this playlist
    click.echo("Fetching tracks from database...")
    cur = conn.cursor()
    cur.execute("SELECT id, playlist_id FROM playlists WHERE playlist_id=?", (playlist_id,))
    track_rows = cur.fetchall()

    if not track_rows:
        click.secho(f"❌ No tracks found for playlist ID: {playlist_id}", fg="red", err=True)
        conn.close()
        sys.exit(1)

    track_ids = [t[0] for t in track_rows]
    click.echo(f"Found {len(track_ids)} tracks")

    # Setup Spotify client
    click.echo("Authenticating with Spotify...")
    try:
        config = load_config()
    except Exception as e:
        click.secho(f"❌ Configuration error: {e}", fg="red", err=True)
        conn.close()
        sys.exit(1)

    auth_params_obj = auth_params(
        client_id=config.spotify.client_id,
        client_secret=config.spotify.client_secret,
        scope=config.spotify.scopes,
        state="state",
    )

    spot_client = spotify(auth_params=auth_params_obj)
    spot_client.get_auth_code_and_tokens()

    # Add tracks to playlist
    try:
        click.echo(f"Adding {len(track_ids)} tracks to playlist...")
        spot_client.add_to_playlist(tracks=track_ids, playlist_id=playlist_id)
        click.secho(f"✓ Successfully added {len(track_ids)} tracks to playlist {playlist_id}", fg="green")
    except Exception as e:
        click.secho(f"❌ Error adding tracks: {e}", fg="red", err=True)
        conn.close()
        sys.exit(1)

    conn.close()


@cli.group()
def db():
    """Database management commands."""
    pass


@db.command()
def migrate():
    """Run database migrations to latest version."""
    import subprocess

    click.echo("Running database migrations...")
    try:
        result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True, check=True)
        click.echo(result.stdout)
        click.secho("✓ Migrations applied successfully", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"❌ Migration failed: {e.stderr}", fg="red", err=True)
        sys.exit(1)


@db.command()
def status():
    """Show current database status."""
    import subprocess

    click.echo("Database status:")
    try:
        result = subprocess.run(["alembic", "current"], capture_output=True, text=True, check=True)
        click.echo(result.stdout)
    except subprocess.CalledProcessError as e:
        click.secho(f"❌ Error: {e.stderr}", fg="red", err=True)
        sys.exit(1)


@db.command()
@click.option("--message", "-m", required=True, help="Migration description")
def create_migration(message):
    """Create a new database migration."""
    import subprocess

    click.echo(f"Creating new migration: {message}")
    try:
        result = subprocess.run(
            ["alembic", "revision", "--autogenerate", "-m", message], capture_output=True, text=True, check=True
        )
        click.echo(result.stdout)
        click.secho("✓ Migration created successfully", fg="green")
    except subprocess.CalledProcessError as e:
        click.secho(f"❌ Error: {e.stderr}", fg="red", err=True)
        sys.exit(1)


@db.command()
def stats():
    """Show database statistics."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Get total playlists
    cur.execute("SELECT COUNT(DISTINCT playlist_id) FROM playlists")
    playlist_count = cur.fetchone()[0]

    # Get total tracks
    cur.execute("SELECT COUNT(*) FROM playlists WHERE id IS NOT NULL")
    track_count = cur.fetchone()[0]

    # Get tracks without Spotify ID (not found)
    cur.execute("SELECT COUNT(*) FROM playlists WHERE id IS NULL")
    not_found_count = cur.fetchone()[0]

    # Get playlists with track counts
    cur.execute(
        """
        SELECT playlist_name, COUNT(*) as track_count
        FROM playlists
        WHERE id IS NOT NULL
        GROUP BY playlist_name
        ORDER BY track_count DESC
        LIMIT 10
    """
    )
    top_playlists = cur.fetchall()

    conn.close()

    # Display statistics
    click.echo("\n" + "=" * 60)
    click.secho("Database Statistics", fg="cyan", bold=True)
    click.echo("=" * 60)
    click.echo(f"Total playlists: {playlist_count}")
    click.echo(f"Total tracks: {track_count}")
    click.echo(f"Tracks not found: {not_found_count}")

    if top_playlists:
        click.echo("\nTop 10 Playlists by Track Count:")
        for name, count in top_playlists:
            click.echo(f"  • {name}: {count} tracks")

    click.echo("=" * 60 + "\n")


# Helper functions


def _get_playlist_tracks_from_db(conn):
    """Get all playlists and their tracks from the database."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT playlist_id, playlist_name, id
        FROM playlists
        WHERE id IS NOT NULL
        ORDER BY playlist_name
    """
    )

    playlists = defaultdict(lambda: {"name": "", "tracks": []})

    for row in cursor.fetchall():
        playlist_id, playlist_name, track_id = row
        if not playlists[playlist_id]["name"]:
            playlists[playlist_id]["name"] = playlist_name
        playlists[playlist_id]["tracks"].append(track_id)

    return dict(playlists)


def _get_spotify_playlist_track_count(spot_client, playlist_id):
    """Get the number of tracks in a Spotify playlist."""
    try:
        result = spot_client._construct_call(f"playlists/{playlist_id}")
        return result["tracks"]["total"]
    except Exception:
        return -1


if __name__ == "__main__":
    cli()
