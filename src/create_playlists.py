from spotify import spotify, auth_params
from classes import env_settings
from playlist_db import get_db_connection
from sqlite3 import Connection


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
    conn = get_db_connection("playlists.db")
    playlist_ids = get_playlist_ids(conn)
    print(playlist_ids)
    settings = env_settings()
    a = auth_params(
        client_id=settings.SPOTIFY_CLIENT_ID,
        client_secret=settings.SPOTIFY_CLIENT_SECRET,
        scope=settings.SPOTIFY_SCOPES,
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
