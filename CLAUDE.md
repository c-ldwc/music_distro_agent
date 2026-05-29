# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project automates creating Spotify playlists from music distributor emails and scraped web pages using AI-powered extraction and search.

**Flow**: Source (email / scraped page) → AI Extraction → AI Search → Spotify API + SQLite DB

## Development Commands

### Package Management
```bash
uv sync                  # Install production dependencies
uv sync --extra dev      # Install with dev dependencies
# To add a dependency: edit pyproject.toml then run uv sync
```

### CLI
```bash
# Process source files and create Spotify playlists
spotify-automation process [--limit N] [--path PATH] [--log-level DEBUG|INFO|WARNING|ERROR]

# Sync playlists from database to Spotify
spotify-automation sync [--log-level DEBUG|INFO|WARNING|ERROR]

# Download new emails from Gmail
spotify-automation download [--log-level DEBUG|INFO|WARNING|ERROR]

# Scrape a URL and save it as a source file for processing
spotify-automation scrape --url URL [-o OUTPUT] [-b/--body] [-s/--script] [-d DATE] [-p PLAYLIST_NAME]
```

The `scrape` command falls back to `curl_cffi` with Chrome impersonation when `httpx` is blocked. Output is a JSON file in `music_source` format, ready for `process`.

### Testing
```bash
pytest                                      # Run all tests
pytest --cov=src --cov-report=term-missing  # With coverage
pytest tests/test_config.py -v              # Specific file
```

### Code Quality
```bash
ruff check --fix .      # Lint and auto-fix
ruff format .           # Format
mypy src/               # Type checking
pre-commit run --all-files
```

### Database Migrations (Alembic)
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic current
alembic downgrade -1
```

## Architecture

### Configuration (`src/config.py`)
Pydantic Settings with sub-configs: `SpotifyConfig`, `AnthropicConfig`, `GmailConfig`, `DatabaseConfig`, `EmailConfig`. Always use `load_config()` — it validates all credentials and file paths at startup with helpful error messages. Services accept config objects; they never read environment variables directly.

### Data Models (`src/classes/classes.py`)
- `music_source`: Source content (date, body, optional playlist_name)
- `extract_release`: AI-extracted release (artist list, album string)
- `album`: Spotify album (artists, title, id)
- `track`: Track metadata (artist, album, track_id)
- `playlist` / `playlist_library`: Collections of albums
- `Agent[T]`: Generic base class — all agents implement `_run()`, use `run()` with retry logic

### AI Agents (`src/agent/agent.py`)
Two Claude-powered agents (LangChain):

**ExtractionAgent** — extracts artist/album pairs from source text
- Raises `NoResultsError` if nothing found; `InvalidResponseError` on bad JSON

**SearchAgent** — searches Spotify for best match
- Confidence levels: EXACT, HIGH, MEDIUM, LOW, NONE
- Returns EXACT/HIGH immediately; falls back to best MEDIUM after 5 strategies:
  1. Full artist list + album title
  2. First artist only
  3. Clean album title (strip "Deluxe", "Remastered", parentheses)
  4. Main title only (split on `:` or `-`)
  5. Simplified artist (remove "feat.", `&` → "and")
- Validates Spotify ID (22 alphanumeric chars) before returning

### Services (`src/services/`)
- **SpotifyService**: Wraps Spotify client and OAuth flow
- **EmailProcessor**: Orchestrates extract → search → cache → record pipeline
  - `process_email_file(file_path, search_tool)` → stats dict
  - `process_all_emails(search_tool, limit)` → summary dict

### Database (`src/db/playlist_db.py`)
SQLite with two tables:
- `playlists`: Tracks with playlist associations; `row_id` is SHA256 of (track_id + playlist_id)
- `album_mappings`: Cache of extracted → Spotify matches; keyed by SHA256 of (artist + album + playlist_id)

All functions take a connection as the first argument. Use `get_db_connection(path)` to get one — it initialises the schema automatically.

### Spotify Client (`src/spotify/spotify.py`)
OAuth2 via a short-lived Flask server on port 5000. Key methods: `search()`, `get_album_tracks()`, `create_playlist()`, `get_playlist_by_name()`, `add_to_playlist()` (chunked at 99 tracks), `playlist_exist()`.

### Utilities
- `src/utils.py` — `is_valid_spotify_id()`: must be exactly 22 alphanumeric characters
- `src/helpers.py` — `retry()`: N retries with random 0.5–1.5s backoff
- `src/email_utils.py` — Gmail API wrapper; handles direct emails and forwarded `.eml` attachments; saves as `music_source` JSON

## Key Patterns

### Always validate Spotify IDs
```python
from src.utils import is_valid_spotify_id
if not is_valid_spotify_id(album.id):
    logger.warning(f"Invalid Spotify ID: '{album.id}'")
    continue
```
The search agent can return malformed IDs; using them causes Spotify API errors.

### Album mapping cache
Check the `album_mappings` table before searching. This avoids redundant Claude + Spotify API calls when the same release appears in multiple emails.

### Search tool for agents
```python
from langchain.tools import tool

@tool
def search(artist: str, album: str):
    """Search Spotify for an album by artist."""
    return [i.model_dump_json() for i in spotify_service.client.search(artist, album)]
```

## Testing

```
tests/
├── conftest.py       # Fixtures: temp_dir, sample_email_data, temp_database, mock_config, etc.
├── test_config.py    # Config validation
├── test_database.py  # DB operations
└── test_models.py    # Pydantic models
```

Mock external APIs (Spotify, Anthropic); use in-memory SQLite for DB tests.

## Logging
- `get_logger(__name__)` in all modules — logs under `spotify_automation.<name>`
- Console: INFO; file (in `logs/`): DEBUG, rotates at 10MB

## Error Handling
- `NoResultsError` — no releases found (common; log at INFO)
- `ExtractionError` / `SearchError` — agent failure (log at ERROR)
- `InvalidResponseError` — bad JSON from agent
- `HTTPStatusError` — Spotify API error

## Standards
- Line length: 120 chars; Ruff enforced via pre-commit
- Never commit: `.env`, `token.json`, `client_secret*.json`, `*.db`
- Main branch: `dev`

## Known Limitations
1. Search agent capped at 5 attempts; may miss unusual editions
2. SQLite only — no concurrent writes
3. No Spotify API rate limiting / retry backoff
4. Source files processed sequentially; no deduplication
5. Each source costs ~2 Claude API calls — rely on album mapping cache
