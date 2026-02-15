import argparse
from sqlite3 import Connection

from src.config import load_config
from src.db import get_db_connection
from src.spotify import auth_params, spotify


def get_playlist_ids(conn: Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("select distinct playlist_id from playlists")
    return [i[0] for i in cur.fetchall()]


def get_playlist_tracks(conn: Connection, playlist_id: str):
    cur = conn.cursor()
    cur.execute(
        """
        select id, playlist_id from playlists where playlist_id=?
                """,
        (playlist_id,),
    )
    track_rows = cur.fetchall()
    return track_rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type="str", help="playlist id")

    args = parser.parse_args()

    conn = get_db_connection("playlists.db")
    playlist_ids = get_playlist_ids(conn)
    print(playlist_ids)
    config = load_config()
    a = auth_params(
        client_id=config.spotify.client_id,
        client_secret=config.spotify.client_secret,
        scope=config.spotify.scopes,
        state="state",
    )

    spot_client = spotify(auth_params=a)
    spot_client.get_auth_code_and_tokens()

    for id in playlist_ids:
        print(f"adding tracks to {id}")
        print(len(id))
        tracks = get_playlist_tracks(conn, id)
        track_ids = [t[0] for t in tracks]
        spot_client.add_to_playlist(tracks=track_ids, playlist_id=id)
