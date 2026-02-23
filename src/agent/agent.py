import json
import logging
import re
from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent
from pydantic import ValidationError

from src import classes
from src.agent.exceptions import ExtractionError, InvalidResponseError, NoResultsError
from src.utils import is_valid_spotify_id

# Get logger for this module
logger = logging.getLogger("spotify_automation.agent")

###
# Prompts and Schemas
###
extraction_prompt = """
You are extracting music releases from a distributor email or website to create Spotify playlists.

EXTRACTION RULES:
1. Extract ALL artist-album pairs mentioned in the email body
2. Include both featured releases and catalog items
3. EXCLUDE:
   - Pre-orders (releases not yet available)
   - Merchandise, tickets, or non-music items
   - Editorial commentary without specific releases
   - Duplicate mentions of the same artist-album pair
   - Albums that are mentioned as part of a description i.e. ("for fans of X", or "Sound like Y")

FORMAT REQUIREMENTS:
- Artists: Return as array, include ALL credited artists (e.g., ["Artist A", "Artist B"])
- Album: Full album title as written, preserve subtitle/edition info
- Handle collaborations: "Artist A & Artist B" or "Artist A feat. Artist B"

QUALITY CHECKS:
- Verify each entry has both artist AND album
- Skip entries that are only artist names without albums
- Preserve original capitalization and punctuation
- Include EPs, singles, and LPs

The email may contain 50-80 releases. Extract them ALL methodically from start to finish.
"""

extraction_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "playlist",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "releases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "artist": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "album": {
                                "type": "string",
                            },
                        },
                        "required": ["artist", "album"],
                    },
                },
            },
            "required": ["title", "releases"],
        },
    },
}

search_prompt = """
You are searching Spotify to find the best match for a music release.

MATCHING CRITERIA (in priority order):
1. Artist name match (primary artist must match closely)
2. Album title match (core title, ignoring edition info)
3. Release type (album/EP/single should match)
4. Ignore differences in:
   - Capitalization (UPPERCASE vs lowercase)
   - Punctuation (hyphens, apostrophes, spacing)
   - Edition markers (Remastered, Deluxe, Vinyl, 180g, year)
   - Featured artist order or "feat." variations

CONFIDENCE LEVELS:
- EXACT: Artist and title match perfectly (ignoring case/punctuation)
- HIGH: Artist matches, title matches core text (ignoring edition info)
- MEDIUM: Artist matches, title has significant overlap (>70% words match)
- LOW: Artist matches, title partially matches (<70% words match)
- NONE: No match found

DECISION RULES:
- Return EXACT or HIGH confidence matches immediately
- Return MEDIUM confidence only if it's the single best option
- Return null (no match) for LOW confidence or no results
- When multiple results, choose the one with most artist overlap

IMPORTANT:
1. Always call the search tool first with the provided artist and album
2. Examine ALL returned results before deciding
3. Return the Spotify album object IF and ONLY IF confidence is MEDIUM or higher
4. Return null if no good match found
"""


search_format = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "title": "SearchResult",
            "type": "object",
            "properties": {
                "album": {"anyOf": [classes.album.model_json_schema(), {"type": "null"}]},
                "confidence": {"type": "string", "enum": ["EXACT", "HIGH", "MEDIUM", "LOW", "NONE"]},
                "reasoning": {"type": "string", "description": "Brief explanation of confidence level"},
            },
            "required": ["album", "confidence", "reasoning"],
        }
    },
}


class ExtractionAgent(classes.Agent[list[classes.extract_release]]):
    prompt: str = extraction_prompt
    response_format: dict[str, Any] = extraction_format

    def _run(self, email: classes.boom_email) -> list[classes.extract_release]:
        """
        Extract releases from email.

        Raises:
            ExtractionError: On failure to extract
            NoResultsError: When no releases found
            InvalidResponseError: When agent returns invalid JSON
        """
        logger.info(f"Starting extraction for email dated {email.date}")
        agent = create_agent(self.model)

        try:
            response = agent.invoke({"messages": [{"role": "user", "content": f"{self.prompt} \n\n {email.body}"}]})[
                "messages"
            ][-1]

            logger.debug("Received response from extraction agent")

            result = json.loads(response.content)

            if not result.get("releases"):
                raise NoResultsError("No releases found in email")

            releases = []
            for item in result["releases"]:
                # Skip if missing artist or album
                if not item.get("artist") or not item.get("album"):
                    logger.warning(f"Skipping incomplete release: {item}")
                    continue

                # Skip if artist list is empty
                if not item["artist"] or len(item["artist"]) == 0:
                    logger.warning(f"Skipping release with no artists: {item.get('album', 'unknown')}")
                    continue

                try:
                    releases.append(classes.extract_release(**item))
                except ValidationError as e:
                    logger.warning(f"Invalid release format: {item} - {e}")
                    continue

            if not releases:
                raise NoResultsError("No valid releases after filtering")

            logger.info(f"Successfully extracted {len(releases)} valid releases")
            return releases

        except json.JSONDecodeError as err:
            logger.error(f"Invalid JSON response: {err}")
            raise InvalidResponseError(f"Failed to parse JSON: {err}") from err

        except NoResultsError:
            raise  # Re-raise, this is expected sometimes

        except Exception as err:
            logger.error(f"Extraction failed: {err}", exc_info=True)
            raise ExtractionError(f"Extraction failed: {err}") from err


class SearchAgent(classes.Agent[classes.album]):
    prompt: str = search_prompt
    response_format: dict[str, Any] = search_format
    max_attempts: int = 5

    def _run(self, release: classes.extract_release, tools: list[Callable[[Any], Any]]) -> classes.album | None:
        """Search with confidence scoring."""
        logger.info(f"Searching for: {release.album} by {', '.join(release.artist)}")

        search_strategies = self._get_search_strategies(release)
        fallback = None

        for attempt, (artist_query, album_query) in enumerate(search_strategies, 1):
            if attempt > self.max_attempts:
                break

            logger.debug(f"Attempt {attempt}: '{artist_query}' - '{album_query}'")

            result, confidence = self._attempt_search(artist_query, album_query, tools)

            # Validate Spotify ID
            if result and not is_valid_spotify_id(result.id):
                logger.warning(f"Invalid Spotify ID '{result.id}', skipping...")
                continue

            # Accept EXACT or HIGH immediately
            if result and confidence in ["EXACT", "HIGH"]:
                logger.info(f"✓ {confidence} match: {result.title}")
                return result

            # Keep MEDIUM as fallback
            elif result and confidence == "MEDIUM" and not fallback:
                fallback = result

        # Return medium confidence fallback if found
        if fallback:
            logger.info(f"⚠ Returning MEDIUM confidence match: {fallback.title}")
            return fallback

        logger.info("✗ No confident match found")
        return None

    def _get_search_strategies(self, release: classes.extract_release) -> list[tuple[str, str]]:
        """Generate different search query variations to try."""
        strategies = []
        artists = release.artist
        album = release.album

        # Strategy 1: Exact match
        strategies.append((", ".join(artists), album))

        # Strategy 2: First artist only
        if len(artists) > 1:
            strategies.append((artists[0], album))

        # Strategy 3: Remove parentheses and edition info
        clean_album = re.sub(r"\s*\([^)]*\)\s*", " ", album)
        clean_album = re.sub(
            r"\s*(Remastered|180g|Vinyl|LP|EP|Edition|Deluxe|Anniversary)\s*", " ", clean_album, flags=re.IGNORECASE
        )
        clean_album = clean_album.strip()
        if clean_album != album:
            strategies.append((", ".join(artists), clean_album))

        # Strategy 4: Remove subtitle (text after : or -)
        main_title = re.split(r"[:\-/]", album)[0].strip()
        if main_title != album:
            strategies.append((", ".join(artists), main_title))

        # Strategy 5: Simplify artist names (& to and, remove feat.)
        simple_artists = [re.sub(r"\b(feat\.|ft\.|featuring)\b", "", a, flags=re.IGNORECASE).strip() for a in artists]
        simple_artists = [a.replace("&", "and") for a in simple_artists if a]
        if simple_artists != artists:
            strategies.append((", ".join(simple_artists), album))

        return strategies

    def _attempt_search(
        self, artist: str, album: str, tools: list[Callable[[Any], Any]]
    ) -> tuple[classes.album | None, str]:
        """Make a single search attempt, return (album, confidence)."""
        agent = create_agent(self.model, tools=tools)

        try:
            response = agent.invoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"{self.prompt} search for the following: Artist: {artist}, Album: {album}",
                        }
                    ]
                },
                tools=tools,
            )["messages"][-1]

            if response.content == "[]" or not response.content:
                return None, "NONE"

            result = json.loads(response.content)

            # Extract album and confidence
            album_data = result.get("album")
            confidence = result.get("confidence", "NONE")
            reasoning = result.get("reasoning", "")

            if album_data is None:
                logger.debug(f"No album found. Reasoning: {reasoning}")
                return None, confidence

            album_result = classes.album(**album_data)
            logger.debug(f"Confidence: {confidence}. Reasoning: {reasoning}")

            return album_result, confidence

        except json.JSONDecodeError as err:
            logger.debug(f"Failed to decode search response: {err}")
            return None, "NONE"
        except (KeyError, TypeError) as err:
            logger.debug(f"Invalid response structure: {err}")
            return None, "NONE"
        except Exception as err:
            logger.debug(f"Search attempt error: {err}")
            return None, "NONE"
