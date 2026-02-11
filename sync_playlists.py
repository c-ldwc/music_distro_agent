"""
Sync playlists from the database to Spotify.

This script:
1. Reads all playlists from the database
2. Connects to Spotify
3. Checks which playlists exist but have no tracks
4. Adds tracks from the database to empty playlists
"""

import sqlite3
from collections import defaultdict

from src.db.playlist_db import get_db_connection
from src.spotify.spotify import auth_params, settings, spotify


def get_playlist_tracks_from_db(conn: sqlite3.Connection) -> dict[str, dict]:
    """
    Get all playlists and their tracks from the database.
    
    Returns:
        dict: {playlist_id: {
            'name': playlist_name,
            'tracks': [track_id1, track_id2, ...]
        }}
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT playlist_id, playlist_name, id 
        FROM playlists 
        WHERE id IS NOT NULL
        ORDER BY playlist_name
    """)

    playlists = defaultdict(lambda: {'name': '', 'tracks': []})

    for row in cursor.fetchall():
        playlist_id, playlist_name, track_id = row
        if not playlists[playlist_id]['name']:
            playlists[playlist_id]['name'] = playlist_name
        playlists[playlist_id]['tracks'].append(track_id)

    return dict(playlists)


def get_spotify_playlist_track_count(spot_client: spotify, playlist_id: str) -> int:
    """
    Get the number of tracks in a Spotify playlist.
    
    Args:
        spot_client: Authenticated Spotify client
        playlist_id: Spotify playlist ID
        
    Returns:
        Number of tracks in the playlist
    """
    try:
        result = spot_client._construct_call(f"playlists/{playlist_id}")
        return result['tracks']['total']
    except Exception as e:
        print(f"Error getting playlist {playlist_id}: {e}")
        return -1


def sync_playlists():
    """
    Main function to sync playlists from database to Spotify.
    """
    # Connect to database
    print("Connecting to database...")
    db_conn = get_db_connection()

    # Get playlists from database
    print("Reading playlists from database...")
    db_playlists = get_playlist_tracks_from_db(db_conn)
    print(f"Found {len(db_playlists)} playlists in database")

    # Setup Spotify client
    print("\nSetting up Spotify connection...")
    setting_vars = settings()
    auth_params_obj = auth_params(
        client_id=setting_vars.SPOTIFY_CLIENT_ID,
        client_secret=setting_vars.SPOTIFY_CLIENT_SECRET,
        scope=setting_vars.SPOTIFY_SCOPES,
        state="state",
    )

    spot_client = spotify(auth_params=auth_params_obj)
    spot_client.get_auth_code_and_tokens()
    print("✅ Connected to Spotify")

    # Check each playlist
    print("\nChecking playlists...")
    synced_count = 0
    skipped_count = 0

    for playlist_id, playlist_data in db_playlists.items():
        playlist_name = playlist_data['name']
        tracks = playlist_data['tracks']

        print(f"\n📋 Checking: {playlist_name} ({playlist_id})")
        print(f"   Database has {len(tracks)} tracks")

        # Check if playlist exists on Spotify
        if not spot_client.playlist_exist(playlist_id):
            print("   ⚠️  Playlist does not exist on Spotify - skipping")
            skipped_count += 1
            continue

        # Check if playlist has tracks
        track_count = get_spotify_playlist_track_count(spot_client, playlist_id)

        if track_count < 0:
            print("   ❌ Error checking playlist - skipping")
            skipped_count += 1
            continue

        if track_count > 0:
            print(f"   ℹ️  Playlist already has {track_count} tracks - skipping")
            skipped_count += 1
            continue

        # Playlist exists but is empty - add tracks
        print(f"   ✨ Playlist is empty - adding {len(tracks)} tracks...")
        try:
            spot_client.add_to_playlist(tracks=tracks, playlist_id=playlist_id)
            print(f"   ✅ Successfully added {len(tracks)} tracks")
            synced_count += 1
        except Exception as e:
            print(f"   ❌ Error adding tracks: {e}")
            skipped_count += 1

    # Close database connection
    db_conn.close()

    # Summary
    print("\n" + "="*50)
    print("Sync complete!")
    print(f"  Synced: {synced_count} playlists")
    print(f"  Skipped: {skipped_count} playlists")
    print("="*50)


if __name__ == "__main__":
    sync_playlists()
