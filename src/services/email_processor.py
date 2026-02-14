"""Email processing service for extracting and matching music releases."""

import json
from pathlib import Path

from httpx import HTTPStatusError

from src import classes
from src.agent.exceptions import ExtractionError, NoResultsError
from src.db import get_album_mapping, record_album_mapping, record_track
from src.utils import is_valid_spotify_id


class EmailProcessor:
    """Processes email files to extract releases and create playlists."""

    def __init__(self, config, spotify_service, agents, db_conn, logger):
        """
        Initialize email processor.

        Args:
            config: Application configuration
            spotify_service: Authenticated Spotify service
            agents: Dict with 'extract' and 'search' agents
            db_conn: Database connection
            logger: Logger instance
        """
        self.config = config
        self.spotify = spotify_service.client
        self.extract_agent = agents["extract"]
        self.search_agent = agents["search"]
        self.db = db_conn
        self.logger = logger

    def process_email_file(self, file_path: Path, search_tool):
        """
        Process a single email file.

        Args:
            file_path: Path to email JSON file
            search_tool: Spotify search tool for agent

        Returns:
            Dict with processing stats (albums_found, albums_not_found, etc.)
        """
        stats = {"albums_found": 0, "albums_not_found": 0, "albums_from_cache": 0, "success": False}

        filename = file_path.name
        self.logger.info(f"Processing email: {filename}")

        try:
            with open(file_path) as f:
                email_data = json.load(f)
                email = classes.boom_email(**email_data)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from {filename}: {e}")
            return stats
        except Exception as e:
            self.logger.error(f"Failed to read email file {filename}: {e}")
            return stats

        # Extract releases
        try:
            extraction_results = self.extract_agent.run(email=email)
        except NoResultsError:
            self.logger.info(f"No releases found in {filename}")
            return stats
        except ExtractionError as e:
            self.logger.error(f"Extraction failed for {filename}: {e}")
            return stats
        except Exception as e:
            self.logger.error(f"Unexpected error extracting from {filename}: {e}", exc_info=True)
            return stats

        # Count unique artists and albums
        all_artists = set()
        all_albums = set()
        for r in extraction_results:
            all_artists.update(r.artist)
            all_albums.add(r.album)

        self.logger.info(f"Extracted {len(all_artists)} unique artists and {len(all_albums)} albums")

        # Create or fetch playlist
        playlist_name = f"Boomkat {email.date.strftime('%Y-%m-%d')}"
        self.logger.info(f"Creating/fetching playlist: {playlist_name}")

        try:
            spot_playlist = self.spotify.get_playlist_by_name(playlist_name)
            if spot_playlist is None:
                spot_playlist = self.spotify.create_playlist(name=playlist_name)
                self.logger.info(f"✓ Created new playlist: {playlist_name}")
            else:
                self.logger.info(f"✓ Found existing playlist: {playlist_name}")
        except Exception as e:
            self.logger.error(f"Failed to create/fetch playlist {playlist_name}: {e}")
            return stats

        found_albums = []

        # Search for each release
        for r in extraction_results:
            extracted_artist = ",".join(r.artist)
            result = None

            # Check cache first
            mapping = get_album_mapping(self.db, extracted_artist, r.album, spot_playlist["id"])

            if mapping and is_valid_spotify_id(mapping["spotify_album_id"]):
                # Use cached mapping
                self.logger.debug(
                    f"◉ Using cached mapping: {r.album} by {extracted_artist} → "
                    f"{mapping['spotify_album']} by {mapping['spotify_artist']}"
                )
                result = classes.album(
                    artists=mapping["spotify_artist"].split(","),
                    title=mapping["spotify_album"],
                    id=mapping["spotify_album_id"],
                )
                stats["albums_from_cache"] += 1
            elif mapping and not is_valid_spotify_id(mapping["spotify_album_id"]):
                # Invalid cached ID
                self.logger.warning(
                    f"Invalid cached ID for {r.album} by {extracted_artist}: '{mapping['spotify_album_id']}', re-searching..."
                )
                mapping = None

            if not mapping:
                # Search Spotify
                try:
                    result = self.search_agent.run(release=r, tools=[search_tool])

                    # Record mapping if valid
                    if result is not None and is_valid_spotify_id(result.id):
                        self.logger.debug(f"✓ Found: {result.title} by {', '.join(result.artists)}")
                        try:
                            record_album_mapping(
                                self.db,
                                extracted_artist,
                                r.album,
                                spot_playlist["id"],
                                ",".join(result.artists),
                                result.title,
                                result.id,
                            )
                        except ValueError as ve:
                            self.logger.error(f"Failed to cache mapping due to invalid ID: {ve}")
                            result = None
                    elif result is not None and not is_valid_spotify_id(result.id):
                        self.logger.warning(f"Search returned invalid ID for {r.album}: '{result.id}'")
                        result = None
                except Exception as e:
                    self.logger.error(f"Search agent failed for {r.album} by {r.artist}: {e}", exc_info=True)
                    stats["albums_not_found"] += 1
                    continue

            if result is not None:
                # Validate ID before using
                if not is_valid_spotify_id(result.id):
                    self.logger.error(f"Skipping album with invalid ID: {result.title} (ID: '{result.id}')")
                    stats["albums_not_found"] += 1
                    continue

                found_albums.append(result)
                stats["albums_found"] += 1

                # Get tracks and record
                try:
                    tracks = self.spotify.get_album_tracks(result.id)

                    for t in tracks:
                        try:
                            record_track(
                                self.db,
                                classes.track(
                                    artist=",".join(result.artists),
                                    album=result.title,
                                    track_id=t,
                                ),
                                playlist_name=playlist_name,
                                playlist_id=spot_playlist["id"],
                            )
                        except Exception as e:
                            self.logger.error(f"Failed to record track {t}: {e}")

                except HTTPStatusError as err:
                    self.logger.error(
                        f"HTTP error retrieving tracks for {result.title} by {','.join(result.artists)}: "
                        f"{err.response.status_code} - {err}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Unexpected error retrieving tracks for {result.title} by {','.join(result.artists)}: {e}",
                        exc_info=True,
                    )
            else:
                stats["albums_not_found"] += 1
                self.logger.debug(f"✗ Not found: {r.album} by {r.artist}")

        self.logger.info(
            f"Processed {filename}: {stats['albums_found']} albums found "
            f"({stats['albums_from_cache']} from cache), {stats['albums_not_found']} not found"
        )
        stats["success"] = True
        return stats

    def process_all_emails(self, search_tool, limit=10):
        """
        Process all emails in the configured directory.

        Args:
            search_tool: Spotify search tool for agents
            limit: Maximum number of emails to process

        Returns:
            Dict with summary stats
        """
        summary = {"processed": 0, "success": 0, "errors": 0, "total_albums_found": 0, "total_albums_not_found": 0}

        self.logger.info(f"Scanning for emails in {self.config.email.path}")

        for dirpath, _, files in self.config.email.path.walk():
            email_files = [f for f in files if ".txt" in f]
            self.logger.info(f"Found {len(email_files)} email files to process")

            for email_file in email_files:
                if summary["processed"] >= limit:
                    self.logger.info(f"Reached processing limit of {limit} emails")
                    break

                summary["processed"] += 1
                file_path = dirpath / email_file

                stats = self.process_email_file(file_path, search_tool)

                if stats["success"]:
                    summary["success"] += 1
                    summary["total_albums_found"] += stats["albums_found"]
                    summary["total_albums_not_found"] += stats["albums_not_found"]
                else:
                    summary["errors"] += 1

        return summary
