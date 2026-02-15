from sqlite3 import Connection

from src.db import get_db_connection


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
    conn = get_db_connection()

    print(
        list(
            conn.cursor().execute(
                "select distinct playlist_id, playlist_name from playlists order by playlist_name desc"
            )
        )
    )
