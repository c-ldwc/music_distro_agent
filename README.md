# Spotify Playlist Automation

Automatically create and sync Spotify playlists from music distributor emails and web scrapes using AI-powered extraction.

## Overview

1. Download emails from Gmail (music distributor newsletters), or scrape a URL directly
2. AI agents extract album/artist information from the content
3. Search Spotify for matching releases
4. Create dated playlists and add found tracks
5. Sync playlists from a local database to Spotify

## Architecture

```
Gmail API → Email Download → AI Extraction Agent → AI Search Agent → Spotify API
                                       ↓
Scraped URL ──────────────────────────→↑
                                       ↓
                                  SQLite DB ← Playlist Sync
```

**Components:**
- **Email Processing**: Downloads and parses emails using Gmail API
- **Web Scraping**: Fetches any URL and saves it as a source for processing
- **AI Extraction Agent**: Uses Claude (Anthropic) to extract artist/album pairs
- **AI Search Agent**: Searches Spotify with retry logic to find matching releases
- **Database**: SQLite storage for tracking playlists, tracks, and processing history
- **Spotify Integration**: Creates/updates playlists and adds tracks

## Prerequisites

- Python 3.13+
- Spotify Developer Account & App
- Google Cloud Project with Gmail API enabled
- Anthropic API key (for Claude AI)

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd spotify
```

### 2. Install Dependencies

Using `uv` (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -e .
```

### 3. Configure Spotify API

1. Create a Spotify app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Note your Client ID and Client Secret
3. Add `http://localhost:8888/callback` to Redirect URIs

### 4. Configure Gmail API

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop application)
4. Download the credentials JSON file
5. Rename it to match the pattern: `client_secret_*.json`

### 5. Get Anthropic API Key

1. Sign up at [Anthropic](https://www.anthropic.com/)
2. Generate an API key from your account dashboard

### 6. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
# Spotify API
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_SCOPES=playlist-modify-public,playlist-modify-private,playlist-read-private

# Anthropic API
ANTHROPIC_API_KEY=your_anthropic_api_key

# Gmail API
GMAIL_SECRET_PATH=client_secret_YOUR_PROJECT.apps.googleusercontent.com.json
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly

# Email Processing
EMAIL_PATH=emails
```

### 7. First Run Authentication

On first run, authenticate with Spotify and Gmail:

```bash
# Opens browser windows for OAuth authentication
python download_emails.py
```

After authentication, `token.json` will be created automatically.

## Usage

### Scrape a URL

```bash
python -m src.cli scrape <url> [--output file.txt] [--body] [--date YYYY-MM-DD] [--playlist-name "My Playlist"]
```

Fetches a URL and saves it as a source file for processing. Options:
- `--body` / `-b`: Extract only the `<body>` text (strips HTML tags)
- `--script` / `-s`: Keep `<script>` tags (only applies with `--body`)
- `--date` / `-d`: Set the source date (defaults to now)
- `--playlist-name` / `-p`: Playlist name to associate with this source

### Download New Emails

```bash
python download_emails.py
```

Downloads unread emails from Gmail and saves them to the configured directory.

### Process Emails and Create Playlists

```bash
python main.py
```

- Reads all source files from the configured directory
- Extracts artist/album information using AI
- Searches Spotify for matches
- Creates dated playlists
- Adds found tracks to playlists
- Records all actions in the database

### Sync Playlists to Spotify

```bash
python sync_playlists.py
```

Syncs tracks from the database to Spotify playlists. Useful if playlists were created but tracks weren't added due to errors.

### Create Individual Playlist

```bash
python create_playlists.py --id <playlist_id>
```

Manually sync a specific playlist by ID from the database to Spotify.

## Project Structure

```
spotify/
├── src/
│   ├── agent/           # AI agents (extraction & search)
│   ├── classes/         # Data models (Pydantic)
│   ├── db/              # Database operations
│   ├── spotify/         # Spotify API client
│   ├── cli.py           # CLI commands (including scrape)
│   ├── config.py        # Configuration validation
│   ├── logging_config.py # Logging setup
│   ├── auth_gmail.py    # Gmail authentication
│   ├── email_utils.py   # Email processing utilities
│   └── helpers.py       # Helper functions
├── tests/               # Test suite
│   ├── conftest.py      # Test fixtures
│   ├── test_config.py   # Configuration tests
│   ├── test_database.py # Database tests
│   └── test_models.py   # Model tests
├── alembic/             # Database migrations
│   └── versions/        # Migration files
├── emails/              # Downloaded email storage
├── logs/                # Application logs
├── main.py              # Main processing script
├── download_emails.py   # Email download script
├── sync_playlists.py    # Playlist sync script
├── create_playlists.py  # Individual playlist creator
├── playlists.db         # SQLite database
├── .env                 # Configuration (not in git)
└── pyproject.toml       # Dependencies
```

## Database Schema

**playlists** table:
- `row_id`: Unique identifier (hash of track_id + playlist_id)
- `id`: Spotify track ID
- `playlist_id`: Spotify playlist ID
- `playlist_name`: Name of the playlist
- `artist`: Artist name(s)
- `album`: Album title
- `attempts`: Number of times track was attempted to add
- `last_attempt`: Timestamp of last attempt

## Configuration

All configuration is managed through environment variables in `.env`:

- **SPOTIFY_CLIENT_ID/SECRET**: Your Spotify app credentials
- **SPOTIFY_SCOPES**: Required Spotify permissions
- **ANTHROPIC_API_KEY**: Claude AI API key
- **GMAIL_SECRET_PATH**: Path to Google OAuth credentials file
- **EMAIL_PATH**: Directory for storing downloaded emails

## Troubleshooting

### Authentication Issues

**Problem**: OAuth authentication fails
**Solution**:
- Verify redirect URIs match in both Spotify/Google dashboards and your config
- Delete `token.json` and re-authenticate
- Check that credentials in `.env` are correct

### No Albums Found

**Problem**: AI extraction finds artists but no Spotify matches
**Solution**:
- Check Spotify search manually to verify album exists
- AI search tries up to 5 attempts with variations
- Some releases may not be on Spotify
- Check logs for search attempts and errors

### Rate Limiting

**Problem**: Spotify API returns 429 errors
**Solution**:
- The application doesn't currently implement rate limiting
- Wait a few minutes before retrying

### Database Locked

**Problem**: `database is locked` error
**Solution**:
- Ensure no other instance of the script is running
- Check for zombie processes: `ps aux | grep python`
- Delete `playlists.db-journal` if it exists

### Gmail API Quota

**Problem**: Gmail API quota exceeded
**Solution**:
- Default quota is 1 billion quota units/day
- Each email list call uses ~5 units
- If exceeded, wait until quota resets (daily)

## Security Notes

⚠️ **CRITICAL SECURITY WARNINGS**:

1. **Never commit credentials to git**
   - `.gitignore` excludes `.env`, `token.json`, and `client_secret*.json`
   - Always use environment variables for secrets
   - If credentials were committed, rotate them immediately

2. **Credential Files**:
   - `client_secret*.json`: Google OAuth credentials
   - `token.json`: Gmail access/refresh tokens (auto-generated)
   - `.env`: All API keys and secrets

3. **Access Scopes**:
   - Spotify: Only playlist modification (not full account access)
   - Gmail: Read-only access

4. **Token Storage**:
   - Tokens are stored locally in plain text
   - Protect your local machine

## Development

For development setup, testing, and contributing guidelines, see [DEVELOPMENT.md](DEVELOPMENT.md).

### Quick Start for Developers

```bash
# Install dev dependencies
uv sync --extra dev

# Set up pre-commit hooks
pre-commit install

# Run tests
pytest

# Run with coverage
pytest --cov=src

# Apply database migrations
alembic upgrade head
```

### Running Tests

```bash
pytest                        # All tests
pytest tests/test_config.py   # Specific file
pytest -v                     # Verbose
```

### Code Quality

```bash
ruff check .          # Linting
ruff format .         # Formatting
mypy src/             # Type checking
bandit -r src/        # Security scan
```

## Known Limitations

- No rate limiting implementation
- Processes all sources sequentially
- SQLite may have concurrency issues with multiple processes
- No deduplication (may reprocess same sources)
- Search agent limited to 5 attempts per album
- No handling of album editions (deluxe, remaster, etc.)

## Contributing

See [DEVELOPMENT.md](DEVELOPMENT.md) for contribution guidelines.

Before submitting:
1. Install pre-commit: `pre-commit install`
2. Run tests: `pytest`
3. Ensure quality checks pass: `pre-commit run --all-files`

## License

[Add your license here]
