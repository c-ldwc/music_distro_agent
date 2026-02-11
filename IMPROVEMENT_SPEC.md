# Repository Improvement Specification

## Project Overview
This repository automates the creation of Spotify playlists from Boomkat music distributor emails using AI agents to extract album/artist information and search Spotify's catalog.

## Critical Issues

### 1. Security & Credentials Management
**Priority: CRITICAL**

- **Issue**: OAuth secrets and tokens are committed to the repository
  - `client_secret_*.json` file is visible in the workspace
  - `token.json` contains authentication tokens
  - `.gitignore` excludes `*secret*` but the file uses a different naming pattern

- **Recommendations**:
  - Move all credentials to environment variables or a secure vault
  - Update `.gitignore` to explicitly exclude:
    ```
    client_secret_*.json
    token.json
    *.json  # except library.json and example configs
    ```
  - Create `client_secret.example.json` with dummy values
  - Add security scanning pre-commit hooks
  - Audit git history to remove committed secrets
  - Rotate all exposed credentials immediately

### 2. Documentation
**Priority: HIGH**

- **Issue**: README.md is completely empty
- **Recommendations**:
  - Add comprehensive README with:
    - Project description and purpose
    - Architecture overview (AI agents → Spotify API flow)
    - Setup instructions (dependencies, OAuth setup, environment variables)
    - Usage guide for each script
    - Configuration guide
    - Troubleshooting section
    - API rate limits and best practices
  - Add inline code documentation/docstrings
  - Create CONTRIBUTING.md for development guidelines
  - Add architecture diagram showing data flow

### 3. Configuration Management
**Priority: HIGH**

- **Issue**: Settings scattered across multiple files
- **Current State**: Uses `env_settings` from classes.py but configuration is implicit
- **Recommendations**:
  - Create `config/` directory with structured configuration
  - Move all settings to `.env.example` template
  - Document all required environment variables
  - Add validation for required environment variables at startup
  - Consider using a configuration library like `dynaconf` or `pydantic-settings` (already using pydantic-settings)
  - Centralize email paths, API endpoints, rate limits

### 4. Error Handling & Resilience
**Priority: HIGH**

**Current Issues**:
- Generic `except Exception` blocks swallow errors ([main.py#L42](main.py#L42), [agent.py#L118](agent.py#L118))
- Silent failures in agent responses
- No retry logic for API failures
- HTTP errors only partially handled ([main.py#L95](main.py#L95))

**Recommendations**:
- Implement specific exception handling for:
  - Spotify API rate limits (429 errors)
  - Network failures
  - Authentication errors
  - Invalid data formats
- Add exponential backoff retry logic
- Implement circuit breaker pattern for external APIs
- Log all errors to file with context
- Add dead letter queue for failed extractions
- Validate email format before processing
- Add timeout configurations for all external calls

### 5. Logging & Monitoring
**Priority: MEDIUM**

**Issues**:
- Uses print statements instead of proper logging
- No structured logging
- No log levels
- No persistent logs

**Recommendations**:
- Replace all `print()` with Python `logging` module
- Implement structured logging (JSON format)
- Add log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Create rotating log files
- Add performance metrics:
  - Processing time per email
  - Success/failure rates
  - API call counts
  - Albums found vs searched
- Consider adding observability tools (Sentry, DataDog)
- Add progress bars for long-running operations (tqdm)

### 6. Database Management
**Priority: MEDIUM**

**Issues**:
- SQLite database (`playlists.db`) not under version control structure
- No database migrations
- Schema management is inline in code
- No indexes defined
- No database backup strategy

**Recommendations**:
- Implement database migrations (Alembic)
- Add indexes on frequently queried columns:
  - `playlist_id`
  - `id` (track_id)
  - `last_attempt`
- Create database schema documentation
- Add database backup/restore scripts
- Implement data retention policies
- Consider PostgreSQL for production
- Add database connection pooling
- Create database utility scripts (backup, cleanup, stats)
- Add constraints and foreign keys

### 7. Code Organization & Architecture
**Priority: MEDIUM**

**Issues**:
- `main.py` contains procedural logic (107 lines)
- Agent classes have mixed concerns
- No clear separation of business logic
- Global scope variables ([main.py#L12-L20](main.py#L12-L20))

**Recommendations**:
- Refactor into proper application structure:
  ```
  src/
    api/          # Spotify/Gmail API clients
    core/         # Business logic
    models/       # Data models (keep classes.py but rename)
    services/     # Orchestration services
    utils/        # Helper functions
    config/       # Configuration management
  ```
- Create a `EmailProcessor` service class
- Implement dependency injection
- Add interfaces/protocols for better testability
- Extract CLI logic from business logic
- Create a proper application entry point
- Use design patterns (Factory, Repository, Strategy)

### 8. Testing
**Priority: HIGH**

**Issue**: No test suite present

**Recommendations**:
- Add `tests/` directory with:
  - Unit tests for all modules
  - Integration tests for API interactions
  - End-to-end tests for complete workflow
- Use pytest as testing framework
- Add test fixtures for sample emails/API responses
- Mock external API calls
- Add code coverage reporting (aim for >80%)
- Implement CI/CD testing pipeline
- Add test data fixtures
- Create property-based tests for data validation

### 9. Code Quality & Standards
**Priority: MEDIUM**

**Issues**:
- Inconsistent code style
- Missing type hints in several places
- Unused import ([download_emails.py#L7](download_emails.py#L7))
- `create_playlists.py` has bug: `args = parser.parse_args` (missing parentheses)
- No linting/formatting enforcement

**Recommendations**:
- Add `ruff` or `pylint` configuration
- Implement `black` for consistent formatting
- Add `mypy` for static type checking
- Configure pre-commit hooks:
  - black (formatting)
  - ruff (linting)
  - mypy (type checking)
  - pytest (tests)
  - security scanning
- Fix all linting errors
- Add type hints everywhere
- Use `pydantic` validation consistently
- Add docstrings to all public functions/classes

### 10. Dependency Management
**Priority: MEDIUM**

**Issues**:
- Minimal dependency specification
- No version pinning beyond minimum
- Using `dotenv` but importing from `python-dotenv`
- No security scanning of dependencies

**Recommendations**:
- Pin all dependency versions
- Use `uv.lock` effectively (already present)
- Add dependency security scanning (safety, pip-audit)
- Document why each dependency is needed
- Consider removing unused dependencies
- Add dependency update automation (Dependabot, Renovate)
- Group dependencies by purpose (dev, prod, testing)

## New Features to Consider

### 11. Email Processing Enhancements
**Priority: LOW**

- **Deduplication**: Track processed emails to avoid reprocessing
- **Email validation**: Verify email format before processing
- **Attachment handling**: Extract from attachments vs body
- **Multiple sources**: Support other music distributors beyond Boomkat
- **Historical processing**: Batch process old emails
- **Email filtering**: Configurable rules for which emails to process

### 12. Spotify Integration Improvements
**Priority: MEDIUM**

- **Playlist management**:
  - Update existing playlists instead of only creating new ones
  - Handle playlist size limits
  - Add playlist descriptions from email content
  - Organize playlists in folders
- **Search improvements**:
  - Better fuzzy matching algorithms
  - Handle multiple search strategies
  - Cache search results
  - Implement similarity scoring for matches
- **Rate limiting**: Implement proper rate limiting to avoid API bans
- **Batch operations**: Use batch API endpoints where available

### 13. AI Agent Improvements
**Priority: MEDIUM**

- **Extraction quality**:
  - Add confidence scores to extractions
  - Implement validation of extracted data
  - Support for remastered/deluxe editions
  - Handle various album format names
- **Search optimization**:
  - Increase max attempts beyond 5 when configured
  - Implement search result caching
  - Add learning from past successful searches
  - Support for artist aliases and alternate names
- **Cost optimization**:
  - Cache LLM responses
  - Batch similar requests
  - Track token usage and costs
  - Implement fallback to cheaper models

### 14. CLI & User Experience
**Priority: LOW**

- **Command-line interface**:
  - Use `click` or `typer` for better CLI
  - Add interactive mode
  - Progress indicators
  - Dry-run mode
  - Configuration wizard
- **Output formatting**:
  - Rich terminal output with colors
  - Summary reports
  - Export results (CSV, JSON)

### 15. Performance Optimization
**Priority: LOW**

- **Concurrency**:
  - Parallel email processing
  - Concurrent API requests (with rate limiting)
  - Async/await for I/O operations
- **Caching**:
  - Cache Spotify search results
  - Cache API responses
  - Implement TTL-based cache invalidation
- **Database optimization**:
  - Batch inserts
  - Connection pooling
  - Query optimization

### 16. DevOps & Deployment
**Priority: MEDIUM**

- **Containerization**:
  - Create Dockerfile
  - Docker Compose for local development
  - Handle secrets in containers
- **CI/CD Pipeline**:
  - GitHub Actions for testing
  - Automated releases
  - Deployment automation
- **Monitoring**:
  - Health check endpoints
  - Performance monitoring
  - Error alerting
- **Scheduling**:
  - Cron job configuration
  - Scheduled email processing
  - Automatic playlist updates

### 17. Data Management
**Priority: LOW**

- **Analytics**:
  - Track success rates
  - Most common extraction failures
  - Popular artists/albums
  - Processing time metrics
- **Export/Import**:
  - Export playlists to JSON
  - Import from other sources
  - Backup utilities
- **Cleanup**:
  - Archive old emails
  - Remove duplicate tracks
  - Prune failed attempts

## Implementation Priority

### Phase 1 (Immediate - Week 1)
1. ✅ Fix security issues - remove credentials from repo
2. ✅ Create comprehensive README
3. ✅ Fix critical bugs (parse_args, unused imports)
4. ✅ Add basic error handling and logging

### Phase 2 (Short-term - Weeks 2-3)
1. ✅ Implement proper configuration management
2. ✅ Add testing framework and initial tests
3. ✅ Set up pre-commit hooks and code quality tools
4. ✅ Database migrations setup

### Phase 3 (Medium-term - Month 2)
1. ✅ Refactor code architecture
2. ✅ Implement comprehensive error handling
3. ✅ Add monitoring and observability
4. ✅ Improve AI agent reliability

### Phase 4 (Long-term - Ongoing)
1. ✅ Performance optimizations
2. ✅ New features based on usage
3. ✅ Advanced Spotify integration
4. ✅ DevOps improvements

## Estimated Effort

- **Security fixes**: 2-4 hours
- **Documentation**: 4-8 hours
- **Testing setup**: 8-16 hours
- **Refactoring**: 16-32 hours
- **New features**: Variable, 4-8 hours each

## Success Metrics

- ✅ Zero security vulnerabilities
- ✅ 80%+ code coverage
- ✅ All linting checks pass
- ✅ Documentation completeness
- ✅ <5% failure rate in album extraction
- ✅ Average processing time <30s per email
- ✅ Zero unhandled exceptions in production
