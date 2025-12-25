import json
from typing import Callable, Any
from httpx import HTTPStatusError
from langchain.agents import create_agent
from langchain.tools import tool

from email_utils import boom_email
from spotify import spotify, auth_params, album
from playlist_db import get_db_connection, record_attempt
import classes

###
# Prompts and Schemas
###
extraction_prompt = """
    The following email is from a music distributor. I want to extract the release titles and artists from
    it. These will be passed to the spotify api to create playlists. Not everything in the email is relevant. I want everything from the Featured New Releases section.
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
    You are an agent designed to search spotify using the search tool. The tool is like any search tool and will return results that may not be relevant.
    This tool takes in an album name and an artist name and returns a list of jsons containing fields for artist, title and id. You can ignore id.
    Find the result that best matches the query. If nothing matches the query. Do not return anything
    The artist and album you are given may not be a perfect match. Please try different combinations or similar words. Finding the album is very important, so do not give up quickly
    Make no more that five search attempts
    """


search_format = {
    "type": "json_schema",
    "json_schema": {
        "schema": {
            "title": "AlbumList",
            "description": "A list of albums with artist and album information.",
            "type": "array",
            "items": album.model_json_schema(),
        }
    },
}


class ExtractionAgent(classes.Agent[list[classes.extract_release]]):
    def _run(self, email: boom_email) -> list[classes.extract_release] | None:
        agent = create_agent(self.model)
        response = agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": f"{self.prompt} \n\n {email.body}"}
                ]
            }
        )["messages"][-1]
        try:
            result = json.loads(response.content)
            releases = []
            for item in result["releases"]:
                releases.append(classes.extract_release(**item))
            return releases
        except json.JSONDecodeError as err:
            print(f"error: {err}")


class searchAgent(classes.Agent[album]):
    def _run(
        self, release: classes.extract_release, tools: list[Callable[[Any], Any]]
    ) -> album | None:
        agent = create_agent(self.model, tools=tools)
        print(f"The release for this run is {release}")
        response = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": f"{self.prompt} search for the following: Artist: {release.artist}, Album: {release.album}",
                    }
                ]
            },
            tools=tools,
        )["messages"][-1]
        try:
            if response.content == "[]":
                return None
            else:
                serialized = json.loads(response.content)[0]
                return album(**serialized)
        except Exception as err:
            print(f"There was an error in search {err}")


if __name__ == "__main__":
    print(search_format)

    settings = classes.env_settings()
    a = auth_params(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        scope=settings.SPOTIFY_SCOPES,
        state="state",
    )

    spot_client = spotify(auth_params=a)
    spot_client.get_auth_code_and_tokens()

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
        print(f"searching for artist {artist} and album {album}")
        try:
            results = spot_client.search(artist, album)
        except Exception as err:
            print(f"there was an error in search: {err}")
        return [i.model_dump_json() for i in results]

    j = 0
    lib = classes.playlist_library()
    extract_agent = ExtractionAgent(
        api_key=settings.ANTHROPIC_API_KEY,
        prompt=extraction_prompt,
        response_format=extraction_format,
    )

    search_agent = searchAgent(
        api_key=settings.ANTHROPIC_API_KEY,
        prompt=search_prompt,
        response_format=search_format,
    )

    db_conn = get_db_connection()

    for dirpath, _, files in settings.email_path.walk():
        for boomkat_file in [i for i in files if ".txt" in i]:
            with open(dirpath / boomkat_file, "r") as f:
                email = boom_email(**json.load(f))
            extraction_results = extract_agent.run(email=email)
            if extraction_results is None:
                continue

            playlist_name = f"Boomkat {email.date.strftime('%Y-%m-%d')}"
            spot_playlist = spot_client.get_playlist_by_name(playlist_name)
            if spot_playlist is None:
                spot_playlist = spot_client.create_playlist(name=playlist_name)
            found_albums: list[album] = []
            for r in extraction_results:
                result = search_agent.run(release=r, tools=[search])
                if result is not None:
                    found_albums.append(result)
                    try:
                        tracks = spot_client.get_album_tracks(result.id)

                        for t in tracks:
                            record_attempt(
                                db_conn,
                                classes.track(
                                    artist=",".join(result.artists),
                                    album=result.title,
                                    track_id=t,
                                ),
                                playlist_name=playlist_name,
                                playlist_id=spot_playlist["id"],
                            )
                    except HTTPStatusError as err:
                        print(
                            f"retrieving tracks for {result.title} by {','.join(result.artists)} failed with error {err}"
                        )

            # spot_client.add_to_playlist(tracks=tracks, playlist_id=spot_playlist["id"])
            j += 1
            if j == 10:
                break
