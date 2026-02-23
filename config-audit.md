# Config Audit: Wired vs. Unused Fields

## Summary

All config fields are now wired through to the classes that use them. Two rounds of fixes were needed.

---

## Round 1: `AnthropicConfig`

| Field | Env key | Was used? | Fix |
|---|---|---|---|
| `api_key` | `ANTHROPIC_API_KEY` | Yes | — |
| `model_name` | `ANTHROPIC_MODEL_NAME` | No | Passed to agent constructors |
| `max_retries` | `ANTHROPIC_MAX_RETRIES` | No | Passed to agent constructors |

**Files changed:** `src/classes/classes.py`, `src/helpers.py`, `main.py`, `src/cli.py`, `.env`

---

## Round 2: remaining configs

### `SpotifyConfig`

| Field | Env key | Was used? | Fix |
|---|---|---|---|
| `client_id` | `SPOTIFY_CLIENT_ID` | Yes | — |
| `client_secret` | `SPOTIFY_CLIENT_SECRET` | Yes | — |
| `scopes` | `SPOTIFY_SCOPES` | Yes | — |
| `redirect_uri` | `SPOTIFY_REDIRECT_URI` | No | Passed to `auth_params` in `SpotifyService.authenticate()` |

Note: `auth_params` had its own hardcoded default `http://127.0.0.1:5000/callback` (different from the `SpotifyConfig` default of `localhost:8888`). `.env` is now set to `http://127.0.0.1:5000/callback` to preserve the working value.

**Files changed:** `src/services/spotify_service.py`, `.env`

---

### `GmailConfig`

| Field | Env key | Was used? | Fix |
|---|---|---|---|
| `secret_path` | `GMAIL_SECRET_PATH` | Yes | — |
| `scopes` | `GMAIL_SCOPES` | Yes | — |
| `token_path` | `GMAIL_TOKEN_PATH` | Yes | — |

No issues.

---

### `DatabaseConfig`

| Field | Env key | Was used? | Fix |
|---|---|---|---|
| `path` | `DATABASE_PATH` | No | Passed to `get_db_connection()` in `main.py` and both `process`/`sync` commands in `src/cli.py` |

`get_db_connection()` accepts a `db_path` argument but was always called with no argument, falling back to its own hardcoded `"playlists.db"`.

**Files changed:** `main.py`, `src/cli.py`, `.env`

---

### `EmailConfig`

| Field | Env key | Was used? | Fix |
|---|---|---|---|
| `path` | `EMAIL_PATH` | Yes | — |
| `max_emails_per_run` | `EMAIL_MAX_EMAILS_PER_RUN` | No | Used as default for `limit` in `main.py` and `src/cli.py` `process` command |

`main.py` hardcoded `limit=10`. `cli.py` `--limit` flag defaulted to `10` instead of reading from config. Changed `--limit` default to `None` and fall back to `config.email.max_emails_per_run` when not provided on the CLI.

**Files changed:** `main.py`, `src/cli.py`, `.env`
