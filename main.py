import json
import sys

from httpx import HTTPStatusError
from langchain.tools import tool

from src import classes
from src.agent import ExtractionAgent, SearchAgent
from src.classes import album
from src.db import get_album_mapping, get_db_connection, record_album_mapping, record_track
from src.logging_config import get_logger, setup_logging
from src.spotify import auth_params, spotify
from src.utils import is_valid_spotify_id

# Setup logging
logger = setup_logging(log_level="INFO")
module_logger = get_logger(__name__)

try:
    settings = classes.env_settings()
except Exception as e:
    logger.error(f"Failed to load environment settings: {e}")
    logger.error("Please ensure .env file is configured correctly")
    raise e

module_logger.info("Initializing Spotify client...")
a = auth_params(
    client_id=settings.SPOTIFY_CLIENT_ID,
    client_secret=settings.SPOTIFY_CLIENT_SECRET,
    scope=settings.SPOTIFY_SCOPES,
    state="state",
)

spot_client = spotify(auth_params=a)

try:
    spot_client.get_auth_code_and_tokens()
    module_logger.info("✓ Spotify authentication successful")
except Exception as e:
    module_logger.error(f"Spotify authentication failed: {e}")
    sys.exit(1)


@tool
def search(artist: str, album: str):
    """
    Args:
        artist: str. The name of the artist to search for
        album:str. The name of the album to search for
    returns:
        list[json string] where the json strings are the search results from the api.
        The strings have the following fields
            artist: the result's artist. There may be multiple,
            title: the title of the release
            id: you can ignore this for decision making.

    """
    module_logger.debug(f"Searching for artist: {artist}, album: {album}")
    try:
        results = spot_client.search(artist, album)
        return [i.model_dump_json() for i in results]
    except HTTPStatusError as err:
        module_logger.error(f"Spotify API error during search: {err.response.status_code} - {err}")
        return []
    except Exception as err:
        module_logger.error(f"Unexpected error in search: {err}", exc_info=True)
        return []


module_logger.info("Initializing AI agents...")
extract_agent = ExtractionAgent(
    api_key=settings.ANTHROPIC_API_KEY,
)

search_agent = SearchAgent(
    api_key=settings.ANTHROPIC_API_KEY,
)

module_logger.info("Connecting to database...")
try:
    db_conn = get_db_connection()
    module_logger.info("✓ Database connection established")
except Exception as e:
    module_logger.error(f"Failed to connect to database: {e}")
    sys.exit(1)

processed_count = 0
success_count = 0
error_count = 0

module_logger.info(f"Scanning for emails in {settings.email_path}")

for dirpath, _, files in settings.email_path.walk():
    email_files = [f for f in files if ".txt" in f]
    module_logger.info(f"Found {len(email_files)} email files to process")

    for boomkat_file in email_files:
        processed_count += 1
        file_path = dirpath / boomkat_file
        module_logger.info(f"Processing email {processed_count}: {boomkat_file}")

        try:
            with open(file_path) as f:
                email_data = json.load(f)
                email = classes.boom_email(**email_data)
        except json.JSONDecodeError as e:
            module_logger.error(f"Failed to parse JSON from {boomkat_file}: {e}")
            error_count += 1
            continue
        except Exception as e:
            module_logger.error(f"Failed to read email file {boomkat_file}: {e}")
            error_count += 1
            continue

        try:
            extraction_results = extract_agent.run(email=email)
        except Exception as e:
            module_logger.error(f"Extraction agent failed for {boomkat_file}: {e}", exc_info=True)
            error_count += 1
            continue

        if extraction_results is None:
            module_logger.warning(f"No releases extracted from {boomkat_file}")
            continue

        # Count and list the number of artists and albums found
        all_artists = set()
        all_albums = set()
        for r in extraction_results:
            all_artists.update(r.artist)
            all_albums.add(r.album)

        module_logger.info(f"Extracted {len(all_artists)} unique artists and {len(all_albums)} albums")
        module_logger.debug(f"Artists: {', '.join(sorted(all_artists)[:10])}{'...' if len(all_artists) > 10 else ''}")

        playlist_name = f"Boomkat {email.date.strftime('%Y-%m-%d')}"
        module_logger.info(f"Creating/fetching playlist: {playlist_name}")

        try:
            spot_playlist = spot_client.get_playlist_by_name(playlist_name)
            if spot_playlist is None:
                spot_playlist = spot_client.create_playlist(name=playlist_name)
                module_logger.info(f"✓ Created new playlist: {playlist_name}")
            else:
                module_logger.info(f"✓ Found existing playlist: {playlist_name}")
        except Exception as e:
            module_logger.error(f"Failed to create/fetch playlist {playlist_name}: {e}")
            error_count += 1
            continue

        found_albums: list[album] = []
        albums_found = 0
        albums_not_found = 0
        albums_from_cache = 0

        for r in extraction_results:
            extracted_artist = ",".join(r.artist)
            result = None
            
            # Check if we already have a mapping for this album
            mapping = get_album_mapping(db_conn, extracted_artist, r.album, spot_playlist["id"])
            
            if mapping and is_valid_spotify_id(mapping["spotify_album_id"]):
                # Use cached mapping if ID is valid
                module_logger.debug(
                    f"◉ Using cached mapping: {r.album} by {extracted_artist} → "
                    f"{mapping['spotify_album']} by {mapping['spotify_artist']}"
                )
                result = album(
                    artists=mapping["spotify_artist"].split(","),
                    title=mapping["spotify_album"],
                    id=mapping["spotify_album_id"],
                )
                albums_from_cache += 1
            elif mapping and not is_valid_spotify_id(mapping["spotify_album_id"]):
                # Invalid cached ID - log and research
                module_logger.warning(
                    f"Invalid cached ID for {r.album} by {extracted_artist}: '{mapping['spotify_album_id']}', re-searching..."
                )
                mapping = None  # Force a new search
            
            if not mapping:
                # No valid mapping found, need to search
                try:
                    result = search_agent.run(release=r, tools=[search])
                    
                    # Record the mapping immediately if a match was found with valid ID
                    if result is not None and is_valid_spotify_id(result.id):
                        module_logger.debug(f"✓ Found: {result.title} by {', '.join(result.artists)}")
                        try:
                            record_album_mapping(
                                db_conn,
                                extracted_artist,
                                r.album,
                                spot_playlist["id"],
                                ",".join(result.artists),
                                result.title,
                                result.id,
                            )
                        except ValueError as ve:
                            module_logger.error(f"Failed to cache mapping due to invalid ID: {ve}")
                            result = None  # Don't use this result
                    elif result is not None and not is_valid_spotify_id(result.id):
                        module_logger.warning(f"Search returned invalid ID for {r.album}: '{result.id}'")
                        result = None  # Reject invalid result
                except Exception as e:
                    module_logger.error(f"Search agent failed for {r.album} by {r.artist}: {e}", exc_info=True)
                    albums_not_found += 1
                    continue

            if result is not None:
                # Double-check ID is valid before using
                if not is_valid_spotify_id(result.id):
                    module_logger.error(f"Skipping album with invalid ID: {result.title} (ID: '{result.id}')")
                    albums_not_found += 1
                    continue
                    
                found_albums.append(result)
                albums_found += 1

                try:
                    tracks = spot_client.get_album_tracks(result.id)

                    for t in tracks:
                        try:
                            record_track(
                                db_conn,
                                classes.track(
                                    artist=",".join(result.artists),
                                    album=result.title,
                                    track_id=t,
                                ),
                                playlist_name=playlist_name,
                                playlist_id=spot_playlist["id"],
                            )
                        except Exception as e:
                            module_logger.error(f"Failed to record track {t}: {e}")

                except HTTPStatusError as err:
                    module_logger.error(
                        f"HTTP error retrieving tracks for {result.title} by {','.join(result.artists)}: "
                        f"{err.response.status_code} - {err}"
                    )
                except Exception as e:
                    module_logger.error(
                        f"Unexpected error retrieving tracks for {result.title} by {','.join(result.artists)}: {e}",
                        exc_info=True
                    )
            else:
                albums_not_found += 1
                module_logger.debug(f"✗ Not found: {r.album} by {r.artist}")

        module_logger.info(
            f"Processed {boomkat_file}: {albums_found} albums found ({albums_from_cache} from cache), {albums_not_found} not found"
        )
        success_count += 1

        # Limit for testing
        if processed_count >= 10:
            module_logger.info("Reached processing limit of 10 emails")
            break

module_logger.info("=" * 60)
module_logger.info("Processing complete!")
module_logger.info(f"Total emails processed: {processed_count}")
module_logger.info(f"Successful: {success_count}")
module_logger.info(f"Errors: {error_count}")
module_logger.info("=" * 60)

if db_conn:
    db_conn.close()
    module_logger.debug("Database connection closed")
