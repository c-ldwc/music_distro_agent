# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project automates creating Spotify playlists from Boomkat music distributor emails using AI-powered extraction and search.

**Flow**: Gmail API → Email Download → AI Extraction → AI Search → Spotify API + SQLite DB

## Development Commands

### Package Management
```bash
# Install dependencies (production)
uv sync

# Install with dev dependencies
uv sync --extra dev

# Add new dependency
# Edit pyproject.toml dependencies array, then:
uv sync
```

### CLI Usage (Unified Interface)
```bash
# Process emails and create playlists
spotify-automation process [--limit N] [--log-level DEBUG|INFO|WARNING|ERROR]

# Sync playlists from database to Spotify
spotify-automation sync [--log-level DEBUG|INFO|WARNING|ERROR]

# Download new emails from Gmail
spotify-automation download [--log-level DEBUG|INFO|WARNING|ERROR]
```

### Legacy Scripts (Still Available)
```bash
# Process emails
python main.py

# Download emails
python download_emails.py

# Sync specific playlist
python sync_playlists.py

# Create individual playlist by ID
python create_playlists.py --id <playlist_id>
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_config.py

# Run specific test
pytest tests/test_config.py::TestSpotifyConfig::test_valid_config

# Verbose output
pytest -v
```

### Code Quality
```bash
# Lint and auto-fix
ruff check --fix .

# Format code
ruff format .

# Type checking
mypy src/

# Security scan
bandit -r src/

# Run all pre-commit hooks
pre-commit run --all-files
```

### Database Migrations (Alembic)
```bash
# Upgrade to latest version
alembic upgrade head

# Create new migration (auto-generate from schema changes)
alembic revision --autogenerate -m "description"

# Show current migration version
alembic current

# View migration history
alembic history

# Downgrade by one version
alembic downgrade -1
```

## Architecture

### Configuration System (`src/config.py`)
- Uses Pydantic Settings for validation with helpful error messages
- Sub-configs: `SpotifyConfig`, `AnthropicConfig`, `GmailConfig`, `DatabaseConfig`, `EmailConfig`
- Always use `load_config()` to get validated configuration
- Configuration errors print user-friendly messages and exit gracefully
- All services should accept config objects, not read environment directly

### AI Agents (`src/agent/`)
Two specialized agents powered by Claude (LangChain):

1. **ExtractionAgent** (`agent.py:138-200`)
   - Extracts artist/album pairs from email text
   - Returns list of `extract_release` objects
   - Raises `NoResultsError` if no releases found
   - Raises `ExtractionError` on failure

2. **SearchAgent** (`agent.py:202-324`)
   - Searches Spotify for best match with confidence scoring
   - Implements 5 search strategies with fallback logic:
     1. Exact match (all artists, full album)
     2. First artist only
     3. Remove edition info (Remastered, 180g, etc.)
     4. Remove subtitle (after : or -)
     5. Simplify artist names (& → and, remove feat.)
   - Returns `album` object or `None`
   - Confidence levels: EXACT, HIGH, MEDIUM, LOW, NONE
   - Only returns EXACT/HIGH/MEDIUM matches
   - Max 5 attempts per release

**Agent Base Class** (`src/classes/classes.py`):
- Generic `Agent[T]` class with `prompt` and `response_format`
- All agents implement `_run()` method
- Agents use `self.model` (ChatAnthropic instance)

### Services Layer (`src/services/`)

1. **SpotifyService** (`spotify_service.py`)
   - Handles Spotify authentication and client initialization
   - Wraps `src.spotify.spotify` client
   - Methods: `authenticate()`, access via `.client`

2. **EmailProcessor** (`email_processor.py`)
   - Orchestrates email → extraction → search → playlist pipeline
   - Implements album mapping cache (DB) to avoid duplicate searches
   - Methods:
     - `process_email_file(file_path, search_tool)`: Single email
     - `process_all_emails(search_tool, limit)`: Batch processing
   - Returns stats dict with counts

### Database (`src/db/`)
- SQLite database: `playlists.db`
- Main table: `playlists` (tracks with playlist associations)
- Key functions in `src/db/playlist_db.py`:
  - `record_track()`: Add track to database
  - `get_album_mapping()`: Retrieve cached search result
  - `record_album_mapping()`: Cache artist/album → Spotify ID mapping
  - `get_db_connection()`: Get SQLite connection
- All database functions expect connection object as first parameter

### Spotify Client (`src/spotify/spotify.py`)
- Wrapper around Spotify Web API
- Key methods:
  - `search(artist, album)`: Returns list of albums
  - `get_album_tracks(album_id)`: Returns track IDs
  - `create_playlist(name)`: Creates playlist
  - `get_playlist_by_name(name)`: Finds existing playlist
  - `add_to_playlist(tracks, playlist_id)`: Adds tracks
  - `playlist_exist(playlist_id)`: Check if playlist exists

### Data Models (`src/classes/classes.py`)
Pydantic models for type safety:
- `boom_email`: Email with date, subject, body
- `extract_release`: Artist list + album title
- `album`: Spotify album (id, title, artists)
- `track`: Track info (track_id, artist, album)
- `Agent[T]`: Generic agent base class

### Logging (`src/logging_config.py`)
- Centralized logging setup with file + console output
- Log files in `logs/` directory with rotation
- Use `get_logger(__name__)` in modules
- Setup via `setup_logging(log_level='INFO')`
- Main logger: `spotify_automation`

## Important Patterns

### Spotify ID Validation
**Critical**: Always validate Spotify IDs before use to prevent API errors.

```python
from src.utils import is_valid_spotify_id

# Check before using
if not is_valid_spotify_id(album.id):
    logger.warning(f"Invalid Spotify ID: '{album.id}'")
    continue

# All database record functions validate IDs automatically
```

**Why**: The search agent sometimes returns invalid IDs (e.g., empty strings, malformed IDs). Using invalid IDs causes Spotify API errors.

### Configuration Access
```python
from src.config import load_config

# Load validated config
config = load_config()

# Access sub-configs
spotify_config = config.spotify
api_key = config.anthropic.api_key
email_path = config.email.path
```

### Agent Usage Pattern
```python
from src.agent import ExtractionAgent, SearchAgent

# Initialize agents
extract_agent = ExtractionAgent(
    api_key=config.anthropic.api_key,
    temperature=0.0
)

search_agent = SearchAgent(
    api_key=config.anthropic.api_key,
    temperature=0.0
)

# Use agents
releases = extract_agent.run(email=email)
album = search_agent.run(release=release, tools=[search_tool])
```

### Database Caching Pattern
The system caches artist/album → Spotify ID mappings to avoid redundant searches:

1. Check cache first: `get_album_mapping(db, artist, album, playlist_id)`
2. If not found, search Spotify via SearchAgent
3. Cache result: `record_album_mapping(db, extracted_artist, extracted_album, playlist_id, spotify_artist, spotify_album, spotify_id)`

This dramatically reduces API calls and AI agent invocations for repeated albums.

### Search Tool Definition
Agents need a search tool to query Spotify:

```python
from langchain.tools import tool

@tool
def search(artist: str, album: str):
    """Search Spotify for an album by artist."""
    results = spotify_client.search(artist, album)
    return [i.model_dump_json() for i in results]

# Pass to SearchAgent
album = search_agent.run(release=release, tools=[search])
```

## Testing Strategy

### Test Structure
```
tests/
├── conftest.py          # Shared fixtures (temp_dir, sample_email_data, etc.)
├── test_config.py       # Configuration validation tests
├── test_database.py     # Database operations tests
└── test_models.py       # Pydantic model tests
```

### Key Fixtures (`tests/conftest.py`)
- `temp_dir`: Temporary directory for tests
- `sample_email_data`: Sample Boomkat email JSON
- `temp_database`: In-memory SQLite database
- `mock_config`: Mock configuration object

### Writing Tests
- Use fixtures for common test setup
- Test config validation errors explicitly
- Mock external APIs (Spotify, Anthropic)
- Use in-memory database for DB tests

## Common Development Tasks

### Adding a New Service
1. Create service class in `src/services/`
2. Accept config object in `__init__`
3. Use dependency injection (pass dependencies, don't create them)
4. Add logging via `get_logger(__name__)`
5. Write tests in `tests/test_<service>.py`

### Modifying Agent Behavior
1. Agent prompts defined at top of `src/agent/agent.py`
2. Response formats use JSON Schema
3. Test changes with real emails (careful of API costs)
4. Update `max_attempts` if needed (SearchAgent default: 5)

### Database Schema Changes
1. Modify schema in code
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Test: `alembic upgrade head`
5. Commit migration file with code changes

### Adding Configuration Options
1. Add field to appropriate config class in `src/config.py`
2. Add validation if needed (`@field_validator`)
3. Update `.env.example` with new variable
4. Update README.md configuration section
5. Add test in `tests/test_config.py`

## Error Handling

### Expected Exceptions
- `NoResultsError`: No releases found (common, log at INFO)
- `ExtractionError`: AI extraction failed (log at ERROR)
- `ValidationError`: Config/model validation failed (print helpful message)
- `HTTPStatusError`: Spotify API error (includes status code, log details)

### Spotify ID Issues
If you see errors like "Invalid album ID", the issue is likely:
1. Agent returned empty/null ID
2. Database has cached invalid ID

Fix by:
1. Always validate IDs with `is_valid_spotify_id()`
2. Re-search if cached ID is invalid
3. Check agent response format

### Database Lock Issues
SQLite can lock with concurrent access:
- Ensure only one process writes at a time
- Close connections properly (`db_conn.close()`)
- Check for zombie processes: `ps aux | grep python`

## Project Standards

### Code Style
- Line length: 120 characters (configured in `pyproject.toml`)
- Ruff for linting/formatting (enforced by pre-commit)
- Type hints encouraged but not required (`mypy` configured permissively)
- Docstrings for public functions (Google style)

### Import Organization
```python
# Standard library
import json
import sys

# Third-party
from langchain.tools import tool
from pydantic import Field

# Local
from src.config import load_config
from src.agent import ExtractionAgent
```

### Logging Levels
- DEBUG: Search attempts, cache hits, API calls
- INFO: Processing progress, found/not found albums
- WARNING: Invalid IDs, missing data, retries
- ERROR: API failures, extraction failures, exceptions

### Git Workflow
- Main branch: `main`
- Working branch pattern: `claude-edits` or feature branches
- Pre-commit hooks run automatically
- Never commit: `.env`, `token.json`, `client_secret*.json`, `*.db`

## Known Limitations & Gotchas

1. **Search Agent Limitations**:
   - Limited to 5 attempts per release
   - Cannot distinguish between editions (Deluxe, Remastered)
   - May miss releases with drastically different titles on Spotify

2. **SQLite Concurrency**:
   - Not suitable for parallel processing
   - Database locks if multiple processes write simultaneously

3. **No Rate Limiting**:
   - Spotify API can return 429 errors under heavy use
   - No automatic retry/backoff implemented

4. **Email Processing**:
   - No deduplication (may reprocess same emails)
   - Processes sequentially (no parallelization)
   - Email files must be in JSON format

5. **API Costs**:
   - Each email processed costs ~2 Claude API calls (extraction + searches)
   - Large emails (50+ releases) cost more due to multiple search attempts
   - Use caching aggressively to reduce costs
