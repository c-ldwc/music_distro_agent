#!/usr/bin/env python3
"""
Utility script to clean up invalid Spotify album IDs from the database cache.
Spotify album IDs should be 22 alphanumeric characters.
"""
import sqlite3
import sys

from src.utils import is_valid_spotify_id


def cleanup_invalid_ids(db_path: str = "playlists.db", dry_run: bool = True):
    """Remove invalid album IDs from the database cache."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Find invalid IDs
    cur.execute("""
        SELECT mapping_id, spotify_album_id, spotify_album, spotify_artist 
        FROM album_mappings
    """)
    
    invalid_count = 0
    valid_count = 0
    
    print("Scanning album_mappings table...")
    print("-" * 80)
    
    for row in cur.fetchall():
        mapping_id, spotify_id, album, artist = row
        if is_valid_spotify_id(spotify_id):
            valid_count += 1
        else:
            invalid_count += 1
            print(f"Invalid ID: '{spotify_id}' | Album: {album} by {artist}")
            if not dry_run:
                cur.execute("DELETE FROM album_mappings WHERE mapping_id=?", (mapping_id,))
    
    if not dry_run:
        conn.commit()
        print("-" * 80)
        print(f"✓ Deleted {invalid_count} invalid entries")
    else:
        print("-" * 80)
        print(f"Found {invalid_count} invalid entries (dry run - not deleted)")
    
    print(f"Valid entries: {valid_count}")
    conn.close()


if __name__ == "__main__":
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No changes will be made")
        print("Use --execute to actually delete invalid entries\n")
    else:
        print("EXECUTE MODE - Invalid entries will be deleted\n")
    
    cleanup_invalid_ids(dry_run=dry_run)
