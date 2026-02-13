# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated Spotify playlist creation from Boomkat music distributor emails using a multi-agent AI system. The application downloads emails via Gmail API, extracts artist/album pairs using Claude AI, searches Spotify for matches, and creates/syncs playlists.

## Development Commands

### Package Management
```bash
# Install dependencies (using uv - recommended)
uv sync

# Install with dev dependencies
uv sync --extra dev

# Alternative with pip
pip install -e .
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_config.py

# Run with coverage report
pytest --cov=src

# Run with verbose output
pytest -v

# Run specific test by name
pytest tests/test_config.py::test_spotify_config_valid -v
```

### Code Quality
```bash
# Lint and check code
ruff check .

# Auto-fix linting issues
ruff check . --fix

# Format code
ruff format .

# Type checking
mypy src/

# Security scan
bandit -r src/

# Run all pre-commit hooks
pre-commit run --all-files
```

### Database Migrations
```bash
# Apply migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"

# Rollback migration
alembic downgrade -1
```

### Application CLI

The project uses a unified CLI interface that consolidates all operations. Use the `./cli` wrapper script (recommended):

```bash
# Show all available commands
./cli --help

# Download emails from Gmail
./cli download

# Process emails and create playlists (main workflow)
./cli process --limit 10 --log-level INFO

# Sync database playlists to Spotify
./cli sync

# Create specific playlist by ID
./cli create --id <playlist_id>

# Database management
./cli db migrate              # Run migrations
./cli db stats                # Show database statistics
./cli db status               # Show migration status
./cli db create-migration -m "description"  # Create new migration
```

**Alternative CLI Access Methods:**
```bash
# Direct Python module execution
.venv/bin/python -m src.cli <command>

# After installing with entry point
spotify-cli <command>
```

**Legacy Scripts** (still available but deprecated):
```bash
python download_emails.py      # Use `spotify-cli download` instead
python main.py                 # Use `spotify-cli process` instead
python sync_playlists.py       # Use `spotify-cli sync` instead
python create_playlists.py     # Use `spotify-cli create` instead
```

## Architecture

### Multi-Agent System

The core of the application uses two specialized AI agents from LangChain:

1. **ExtractionAgent** (`src/agent/agent.py:138`)
   - Extracts artist/album pairs from email body text
   - Uses structured JSON output format with Pydantic validation
   - Filters out pre-orders, merchandise, and incomplete entries
   - Returns list of `extract_release` objects

2. **SearchAgent** (`src/agent/agent.py:202`)
   - Searches Spotify for extracted releases with confidence scoring
   - Implements 5 search strategies with progressively relaxed queries
   - Confidence levels: EXACT, HIGH, MEDIUM, LOW, NONE
   - Returns `album` object with Spotify metadata only for MEDIUM+ confidence

Both agents use Claude Haiku (default model: `claude-haiku-4-5-20251001`) and have retry logic with fallback strategies.

### Configuration System (`src/config.py`)

Centralized configuration using Pydantic Settings with validation:

- **SpotifyConfig**: OAuth credentials, scopes, redirect URI
- **AnthropicConfig**: API key, model selection, retry settings
- **GmailConfig**: OAuth credentials path, token storage
- **DatabaseConfig**: SQLite database path
- **EmailConfig**: Email storage directory, processing limits

**Important**: Configuration validates on startup. Use `AppConfig()` to load and validate all configs. Invalid/missing credentials trigger helpful error messages with setup instructions.

### Service Layer (`src/services/`)

Encapsulates external API interactions:

- **SpotifyService**: Handles Spotify authentication and provides authenticated client
- **EmailProcessor**: Processes emails through the full extraction → search → playlist creation workflow

Services consume config objects and provide clean interfaces to underlying APIs.

### Database Schema (`src/db/playlist_db.py`)

**playlists** table:
- `row_id`: SHA256 hash of (track_id + playlist_id) - PRIMARY KEY
- `id`: Spotify track ID
- `playlist_id`: Spotify playlist ID
- `playlist_name`: Human-readable playlist name
- `artist`: Artist name(s)
- `album`: Album title
- `attempts`: Retry counter for failed additions
- `last_attempt`: Timestamp of last attempt

**album_mappings** table:
- Caches successful album searches to avoid duplicate AI queries
- Maps extracted artist/album to Spotify album ID
- Keyed by (extracted_artist, extracted_album, playlist_id)

### Resilience Patterns (`src/resilience.py`)

New module providing:
- **Retry with exponential backoff**: Automatic retries with jitter for transient failures
- **Circuit breaker**: Protects against cascading failures by temporarily blocking requests
- **Rate limiting**: Token bucket implementation for API quota management

Use decorators `@retry()` and `@circuit_breaker()` on functions making external API calls.

### Data Models (`src/classes/classes.py`)

Pydantic models for type safety:
- `boom_email`: Email with date, subject, body
- `extract_release`: Artist list + album title extracted from email
- `album`: Full Spotify album metadata (id, title, artists, release_date, etc.)
- `track`: Individual Spotify track with URI

## Key Workflows

### Email Processing Pipeline

1. **Download** (`download_emails.py`): Gmail API → save as text files in `boomkat_emails/`
2. **Extract** (`main.py`): Text → ExtractionAgent → list of releases
3. **Search** (`main.py`): Each release → SearchAgent → Spotify album (or None)
4. **Create Playlist** (`main.py`): Group tracks by date → create dated playlist
5. **Add Tracks**: First 10 tracks from each album → playlist
6. **Record**: All actions logged to SQLite database

### Retry & Error Handling

- **ExtractionAgent**: Raises `ExtractionError`, `NoResultsError`, or `InvalidResponseError`
- **SearchAgent**: Returns `None` on failure (no exception), retries with different query strategies
- **Spotify API**: Use `src/helpers.py` retry utilities for rate limiting and transient errors
- **Database**: Connection errors logged, operations are atomic with `conn.commit()`

## Important Patterns

### Agent Invocation
```python
# Extraction
agent = ExtractionAgent(model=chat_model, response_format=extraction_format)
releases = agent._run(email=boom_email_obj)

# Search (requires tools for Spotify API calls)
search_agent = SearchAgent(model=chat_model, response_format=search_format)
album = search_agent._run(release=extract_release_obj, tools=[spotify_search_tool])
```

### Configuration Loading
```python
from src.config import load_config

config = load_config(validate=True)  # Exits with error messages if invalid
spotify_service = SpotifyService(config.spotify)
client = spotify_service.authenticate()
```

### Database Operations
```python
from src.db.playlist_db import get_db_connection, record_track

conn = get_db_connection()  # Creates tables if not exist
record_track(conn, track_obj, playlist_name, playlist_id)
conn.close()
```

## Testing Strategy

- **Unit tests**: Models, config validation, database operations
- **Integration tests**: Agent responses, Spotify API mocks
- **Fixtures** (`tests/conftest.py`): Provide mock config, test data, temp databases
- **Coverage**: Target 80%+ for `src/` directory (excluding agent prompt texts)

When writing tests:
- Use `tmp_path` fixture for file operations
- Mock external APIs (Spotify, Anthropic, Gmail)
- Test both success and failure paths
- Validate Pydantic models with invalid data

## Common Gotchas

1. **Spotify ID Validation**: Always validate with `is_valid_spotify_id()` (must be exactly 22 base62 characters). Invalid IDs will fail when adding to playlists.

2. **Agent Response Formats**: Both agents require `response_format` parameter with strict JSON schema. Missing or incorrect schema causes silent failures.

3. **Configuration Environment**: `.env` file must exist and contain valid credentials. Use `.env.example` as template. Missing credentials trigger detailed validation errors on startup.

4. **Database Locking**: SQLite has limited concurrency. Don't run multiple scripts simultaneously. Check for `playlists.db-journal` if you get lock errors.

5. **Gmail Token Refresh**: `token.json` is auto-created on first OAuth flow. Delete it to re-authenticate if you get auth errors.

6. **Pre-commit Hooks**: Automatically run tests, linting, type checking, and security scans. Failures block commits. Use `--no-verify` only when absolutely necessary.

## File Organization

```
src/
├── agent/              # AI agents (extraction & search)
│   ├── agent.py        # ExtractionAgent, SearchAgent classes
│   └── exceptions.py   # Agent-specific exceptions
├── classes/            # Pydantic data models
├── db/                 # Database operations
├── services/           # Service layer (Spotify, Email)
├── spotify/            # Spotify API client & auth
├── config.py           # Configuration validation
├── resilience.py       # Retry, circuit breaker, rate limiting
├── metrics.py          # Performance monitoring (new)
└── logging_config.py   # Centralized logging setup

Root scripts:
- main.py              # Primary workflow orchestrator
- download_emails.py   # Gmail downloader
- sync_playlists.py    # DB → Spotify sync
- create_playlists.py  # Individual playlist creation
```

## Environment Variables

Required in `.env`:
```bash
SPOTIFY_CLIENT_ID=<from Spotify Developer Dashboard>
SPOTIFY_CLIENT_SECRET=<from Spotify Developer Dashboard>
SPOTIFY_SCOPES=playlist-modify-public,playlist-modify-private,playlist-read-private

ANTHROPIC_API_KEY=<from Anthropic Console>
ANTHROPIC_MODEL_NAME=claude-haiku-4-5-20251001

GMAIL_SECRET_PATH=client_secret_*.json
GMAIL_SCOPES=https://www.googleapis.com/auth/gmail.readonly

EMAIL_PATH=boomkat_emails
EMAIL_MAX_EMAILS_PER_RUN=10

DATABASE_PATH=playlists.db
```

## Recent Changes (dev branch)

The codebase has undergone significant refactoring:
- Centralized config system with validation (replacing scattered env vars)
- Service layer abstraction for Spotify and email processing
- Resilience patterns for API reliability
- Metrics collection for performance monitoring
- Comprehensive test suite with 30+ tests
- Pre-commit hooks enforcing code quality

When making changes, maintain these architectural patterns.
