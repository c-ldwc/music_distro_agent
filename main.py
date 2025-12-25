import json
from typing import Callable, Any
from langchain.agents import create_agent

from src import classes

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
            "items": classes.album.model_json_schema(),
        }
    },
}


class ExtractionAgent(classes.Agent[list[classes.extract_release]]):
    prompt: str = extraction_prompt
    response_format: dict[str, Any] = extraction_format

    def _run(self, email: classes.boom_email) -> list[classes.extract_release] | None:
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


class SearchAgent(classes.Agent[classes.album]):
    prompt: str = search_prompt
    response_format: dict[str, Any] = search_format

    def _run(
        self, release: classes.extract_release, tools: list[Callable[[Any], Any]]
    ) -> classes.album | None:
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
                return classes.album(**serialized)
        except Exception as err:
            print(f"There was an error in search {err}")
