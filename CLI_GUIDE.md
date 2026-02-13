# CLI Guide

## Quick Start

The Spotify Playlist Automation CLI provides a unified interface for all operations.

### Basic Usage

```bash
./cli --help                  # Show all commands
./cli <command> --help        # Get help for specific command
```

## Commands

### 1. Download Emails

Download new Boomkat emails from Gmail:

```bash
./cli download
```

Options:
- `--log-level [DEBUG|INFO|WARNING|ERROR]` - Set logging verbosity

### 2. Process Emails

Process emails and create playlists (main workflow):

```bash
./cli process
```

Options:
- `--limit INTEGER` - Maximum number of emails to process (default: 10)
- `--log-level [DEBUG|INFO|WARNING|ERROR]` - Set logging verbosity

Example:
```bash
./cli process --limit 5 --log-level DEBUG
```

This command:
1. Reads email files from the configured directory
2. Extracts artist/album information using AI
3. Searches Spotify for matches
4. Creates dated playlists (e.g., "Boomkat 2026-02-05")
5. Adds found tracks to playlists
6. Records all actions in the database

### 3. Sync Playlists

Sync playlists from database to Spotify:

```bash
./cli sync
```

Checks all playlists in the database and adds tracks to empty Spotify playlists.

Options:
- `--log-level [DEBUG|INFO|WARNING|ERROR]` - Set logging verbosity

### 4. Create Specific Playlist

Create or update a specific playlist by ID:

```bash
./cli create --id <playlist_id>
```

Required:
- `--id TEXT` - Spotify playlist ID

Example:
```bash
./cli create --id 37i9dQZF1DXcBWIGoYBM5M
```

### 5. Database Management

#### Show Statistics

View database statistics including playlist counts and top playlists:

```bash
./cli db stats
```

Example output:
```
============================================================
Database Statistics
============================================================
Total playlists: 15
Total tracks: 487
Tracks not found: 23

Top 10 Playlists by Track Count:
  • Boomkat 2026-02-10: 52 tracks
  • Boomkat 2026-02-03: 48 tracks
  ...
============================================================
```

#### Run Migrations

Apply all pending database migrations:

```bash
./cli db migrate
```

#### Check Migration Status

Show current database migration status:

```bash
./cli db status
```

#### Create New Migration

Create a new database migration:

```bash
./cli db create-migration -m "Add new column to playlists"
```

## Configuration

The CLI uses configuration from your `.env` file. Ensure all required credentials are set:

- `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`
- `ANTHROPIC_API_KEY`
- `GMAIL_SECRET_PATH`

See `.env.example` for a complete template.

## Troubleshooting

### Command Not Found

If `./cli` doesn't work:

1. Make sure the script is executable:
   ```bash
   chmod +x cli
   ```

2. Ensure virtual environment exists:
   ```bash
   uv sync
   ```

### Authentication Errors

For Gmail or Spotify authentication issues:

1. Delete existing tokens:
   ```bash
   rm token.json  # Gmail token
   ```

2. Re-run the command to trigger OAuth flow

### Configuration Errors

The CLI will show detailed error messages for missing or invalid configuration. Follow the on-screen instructions to fix issues.

## Alternative CLI Access

### Using Python Module Directly

```bash
.venv/bin/python -m src.cli <command>
```

### Using Installed Entry Point

After `uv sync`, you can use:

```bash
spotify-cli <command>
```

(Requires `tool.uv.package = true` in pyproject.toml)

## Examples

### Complete Workflow

```bash
# 1. Download new emails
./cli download

# 2. Process the first 10 emails
./cli process --limit 10

# 3. Check what was added
./cli db stats

# 4. Sync any empty playlists
./cli sync
```

### Debugging Issues

```bash
# Run with debug logging
./cli process --limit 1 --log-level DEBUG

# Check database state
./cli db stats
./cli db status
```

### Database Maintenance

```bash
# Check current migration status
./cli db status

# Apply pending migrations
./cli db migrate

# Create a new migration after model changes
./cli db create-migration -m "Add album_mappings table"
```

## Getting Help

For any command, use `--help`:

```bash
./cli --help
./cli process --help
./cli db --help
./cli db create-migration --help
```
