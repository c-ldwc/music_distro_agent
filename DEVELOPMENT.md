# Development Guide

## Setup for Development

### 1. Install Development Dependencies

```bash
# Install with dev dependencies
uv sync --extra dev

# Or with pip
pip install -e ".[dev]"
```

### 2. Set Up Pre-commit Hooks

```bash
pre-commit install
```

This will run code quality checks before each commit:
- Ruff (linting and formatting)
- MyPy (type checking)
- Bandit (security scanning)
- Pytest (tests)
- Various file checks

### 3. Manual Pre-commit Run

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run ruff --all-files
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_config.py

# Run specific test
pytest tests/test_config.py::TestSpotifyConfig::test_valid_config

# Run with coverage
pytest --cov=src --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_config.py        # Configuration tests
├── test_database.py      # Database tests
└── test_models.py        # Data model tests
```

### Writing Tests

Use provided fixtures for common test needs:

```python
def test_example(temp_dir, sample_email_data, temp_database):
    # temp_dir: Temporary directory
    # sample_email_data: Sample email JSON
    # temp_database: SQLite test database
    pass
```

## Code Quality

### Linting and Formatting

```bash
# Check linting
ruff check .

# Auto-fix linting issues
ruff check --fix .

# Format code
ruff format .
```

### Type Checking

```bash
# Run mypy
mypy src/

# Run on specific file
mypy src/config.py
```

### Security Scanning

```bash
# Run bandit
bandit -r src/
```

## Database Migrations

### Initial Setup

The database migrations are managed with Alembic.

### Create a Migration

```bash
# Auto-generate migration from schema changes
alembic revision --autogenerate -m "description of changes"

# Create empty migration
alembic revision -m "description of changes"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade by 1 version
alembic upgrade +1

# Downgrade by 1 version
alembic downgrade -1

# Downgrade to base (empty database)
alembic downgrade base
```

### View Migration History

```bash
# Show current version
alembic current

# Show migration history
alembic history

# Show history with verbose output
alembic history --verbose
```

### Migration Best Practices

1. **Always review auto-generated migrations** before applying
2. **Test migrations** on a copy of production data
3. **Write downgrade paths** for all migrations
4. **Keep migrations small** and focused
5. **Add indexes** for frequently queried columns

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

### Configuration Validation

The new config module validates all settings on startup:

```python
from src.config import load_config

# Load and validate
config = load_config()

# Access sub-configurations
print(config.spotify.client_id)
print(config.anthropic.api_key)
```

## Project Structure

```
spotify/
├── src/
│   ├── config.py          # NEW: Configuration validation
│   ├── logging_config.py  # Logging setup
│   ├── agent/             # AI agents
│   ├── classes/           # Data models
│   ├── db/                # Database operations
│   └── spotify/           # Spotify API client
├── tests/                 # NEW: Test suite
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_database.py
│   └── test_models.py
├── alembic/               # NEW: Database migrations
│   ├── versions/
│   └── env.py
├── alembic.ini            # Alembic configuration
├── pyproject.toml         # Updated with dev dependencies
└── .pre-commit-config.yaml # Updated with more hooks
```

## Common Tasks

### Before Committing

```bash
# 1. Format code
ruff format .

# 2. Fix linting issues
ruff check --fix .

# 3. Run tests
pytest

# 4. Check types
mypy src/

# Pre-commit will also run these automatically
```

### Adding a New Dependency

```bash
# Add to pyproject.toml dependencies array
# Then sync
uv sync
```

### Updating Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add package@latest
```

## Troubleshooting

### Tests Failing

- Ensure `.env` is not interfering (tests use fixtures)
- Check that temporary directories are being cleaned up
- Run with `-v` flag for verbose output

### Pre-commit Hooks Failing

- Run manually: `pre-commit run --all-files`
- Update hooks: `pre-commit autoupdate`
- Skip if necessary: `git commit --no-verify` (not recommended)

### Type Checking Errors

- Add `# type: ignore` for known issues
- Update type stubs: `pip install types-*`
- Configure in `pyproject.toml` under `[tool.mypy]`

### Migration Issues

- Check current version: `alembic current`
- Verify database schema matches: `sqlite3 playlists.db .schema`
- Start fresh: Delete `playlists.db` and run `alembic upgrade head`

## CI/CD (Future)

When setting up CI/CD, run:

```bash
# Install dependencies
uv sync --extra dev

# Run quality checks
ruff check .
mypy src/
bandit -r src/

# Run tests with coverage
pytest --cov=src --cov-report=xml

# Apply migrations
alembic upgrade head
```
