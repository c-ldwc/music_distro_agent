import json
import logging
import re
from collections.abc import Callable
from typing import Any

from langchain.agents import create_agent

from src import classes
from src.utils import is_valid_spotify_id

# Get logger for this module
logger = logging.getLogger("spotify_automation.agent")

###
# Prompts and Schemas
###
extraction_prompt = """
    The following email is from a music distributor. I want to extract the release titles and artists from
    it. These will be passed to the spotify api to create playlists. Not everything in the email is relevant.
    I want artist and album pairing featured in the email. Assume everything I send you is intended to be read.
    Search the entire text and do not stop until you have read the whole thing, there may be as many as 80 releases mentioned
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
    You are an agent designed to search spotify using the search tool. The tool returns results that may not be exact matches.
    This tool takes in an album name and an artist name and returns a list of jsons containing fields for artist, title and id.
    Find the result that best matches the query.
    
    IMPORTANT: You MUST call the search tool to find matches. Examine results carefully - Spotify results often have:
    - Different capitalization (UPPERCASE vs lowercase)
    - Different punctuation or special characters
    - Featured artists in different order
    - Album titles with/without edition info (Remastered, Vinyl, year, etc.)
    
    If you find a result that is clearly the same album (even with minor name differences), return it.
    If no results match after searching, return an empty array [].
    """


search_format = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "title": "AlbumList",
            "description": "A list of albums with artist and album information.",
            "type": "array",
            "items": classes.album.model_json_schema(),
        }
    },
}


class ExtractionAgent(classes.Agent[list[classes.extract_release]]):
    prompt: str = extraction_prompt
    response_format: dict[str, Any] = extraction_format

    def _run(self, email: classes.boom_email) -> list[classes.extract_release] | None:
        logger.info(f"Starting extraction for email dated {email.date}")
        agent = create_agent(self.model)

        try:
            response = agent.invoke(
                {
                    "messages": [
                        {"role": "user", "content": f"{self.prompt} \n\n {email.body}"}
                    ]
                }
            )["messages"][-1]

            logger.debug("Received response from extraction agent")

            result = json.loads(response.content)
            releases = []
            for item in result["releases"]:
                releases.append(classes.extract_release(**item))

            logger.info(f"Successfully extracted {len(releases)} releases")
            return releases

        except json.JSONDecodeError as err:
            logger.error(f"Failed to decode JSON response: {err}")
            logger.debug(f"Response content: {response.content[:200]}...")
            return None
        except KeyError as err:
            logger.error(f"Missing expected key in response: {err}")
            return None
        except Exception as err:
            logger.error(f"Unexpected error during extraction: {err}", exc_info=True)
            return None


class SearchAgent(classes.Agent[classes.album]):
    prompt: str = search_prompt
    response_format: dict[str, Any] = search_format
    max_attempts: int = 5

    def _run(
        self, release: classes.extract_release, tools: list[Callable[[Any], Any]]
    ) -> classes.album | None:
        """Search for an album with multiple retry strategies."""
        logger.info(f"Searching for: {release.album} by {', '.join(release.artist)}")
        
        # Define search strategies
        search_strategies = self._get_search_strategies(release)
        
        for attempt, (artist_query, album_query) in enumerate(search_strategies, 1):
            if attempt > self.max_attempts:
                break
                
            logger.debug(f"Attempt {attempt}/{self.max_attempts}: Artist='{artist_query}', Album='{album_query}'")
            
            try:
                result = self._attempt_search(artist_query, album_query, tools)
                if result and is_valid_spotify_id(result.id):
                    logger.info(
                        f"✓ Found match on attempt {attempt}: {result.title} by {', '.join(result.artists)}"
                    )
                    return result
                elif result and not is_valid_spotify_id(result.id):
                    logger.warning(f"Invalid Spotify ID returned: '{result.id}', retrying...")
                    
            except Exception as err:
                logger.debug(f"Attempt {attempt} failed: {err}")
                continue
        
        logger.info(f"No match found after {min(len(search_strategies), self.max_attempts)} attempts: {release.album} by {', '.join(release.artist)}")
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
        clean_album = re.sub(r'\s*\([^)]*\)\s*', ' ', album)
        clean_album = re.sub(r'\s*(Remastered|180g|Vinyl|LP|EP|Edition|Deluxe|Anniversary)\s*', ' ', clean_album, flags=re.IGNORECASE)
        clean_album = clean_album.strip()
        if clean_album != album:
            strategies.append((", ".join(artists), clean_album))
        
        # Strategy 4: Remove subtitle (text after : or -)
        main_title = re.split(r'[:\-/]', album)[0].strip()
        if main_title != album:
            strategies.append((", ".join(artists), main_title))
        
        # Strategy 5: Simplify artist names (& to and, remove feat.)
        simple_artists = [re.sub(r'\b(feat\.|ft\.|featuring)\b', '', a, flags=re.IGNORECASE).strip() for a in artists]
        simple_artists = [a.replace('&', 'and') for a in simple_artists if a]
        if simple_artists != artists:
            strategies.append((", ".join(simple_artists), album))
        
        return strategies

    def _attempt_search(
        self, artist: str, album: str, tools: list[Callable[[Any], Any]]
    ) -> classes.album | None:
        """Make a single search attempt."""
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
                return None
            
            serialized = json.loads(response.content)[0]
            album_result = classes.album(**serialized)
            return album_result

        except json.JSONDecodeError as err:
            logger.debug(f"Failed to decode search response: {err}")
            return None
        except (IndexError, KeyError) as err:
            logger.debug(f"Invalid response structure: {err}")
            return None
        except Exception as err:
            logger.debug(f"Search attempt error: {err}")
            return None
