from src.agent import ExtractionAgent, SearchAgent
from src.spotify import spotify, album, auth_params
from src.db import record_track, get_db_connection
from langchain.tools import tool
import json
from src import classes
from httpx import HTTPStatusError


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
        return [json.dumps(i) for i in results]
    except Exception as err:
        print(f"there was an error in search: {err}")


j = 0
extract_agent = ExtractionAgent(
    api_key=settings.ANTHROPIC_API_KEY,
)

search_agent = SearchAgent(
    api_key=settings.ANTHROPIC_API_KEY,
)

db_conn = get_db_connection()

for dirpath, _, files in settings.email_path.walk():
    for boomkat_file in [i for i in files if ".txt" in i]:
        with open(dirpath / boomkat_file, "r") as f:
            email = classes.boom_email(**json.load(f))
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
                except HTTPStatusError as err:
                    print(
                        f"retrieving tracks for {result.title} by {','.join(result.artists)} failed with error {err}"
                    )

        # spot_client.add_to_playlist(tracks=tracks, playlist_id=spot_playlist["id"])
        j += 1
        if j == 10:
            break
