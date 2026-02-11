from src.db import get_db_connection, drop_playlist

conn = get_db_connection()

cur = conn.cursor()
cur.execute("Select distinct playlist_name, playlist_id from playlists where playlist_name like '%2026-02%'")

mapping = cur.fetchall()[0][1]
print(mapping)
cur.execute("DELETE from playlists where playlist_name like '%2026-02%'")

cur.execute("DELETE from album_mappings where playlist_id=?", (mapping,))

cur.execute("Select distinct playlist_name, playlist_id from playlists where playlist_name like '%2026-02%'")
print(cur.fetchall())

cur.execute("select * from album_mappings where playlist_id=?", (mapping,))

print(cur.fetchall())
