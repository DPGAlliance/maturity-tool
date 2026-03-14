# Scripts

## `scripts/refresh_cache.py`
Refreshes cached raw data and writes a metrics snapshot for each repo.

### Setup (scripts env)
```bash
cd scripts
poetry install
```

### Usage
```bash
poetry run python refresh_cache.py --owner <org>
```

### Options
- `--owner <org>` : GitHub owner/org (required unless using `DISTINGUISHED_OWNERS`).
- `--repo <name>` : Limit to a single repo.
- `--force-refresh` : Ignore cache age and refetch.

## `scripts/refresh_scheduler.py`
Runs `refresh_cache.collect_for_repo(...)` on an interval (useful in Docker Compose without cron).

When enabled (default), it also runs `scripts/summarize.py` after the refresh completes, so summaries stay in sync with the latest metrics.

### Env
- `REFRESH_OWNERS=owner1,owner2` (recommended)
- `REFRESH_REPO` (optional, single repo name)
- `REFRESH_INTERVAL_DAYS` (default: `7`)
- `REFRESH_INTERVAL_SECONDS` (optional override; primarily for testing)
- `FORCE_REFRESH` (default: `false`)

Summaries (run after refresh):
- `RUN_SUMMARIES` (default: `true`)
- `SUMMARY_BASE_URL` (default: `http://api:8000` in Docker Compose)
- `SUMMARY_MODEL` (optional)
- `SUMMARY_HISTORY` (optional)
- `SUMMARY_MAX_AGE_DAYS` (optional)
- `SUMMARY_FORCE` (optional)
- `SUMMARY_NO_STORE` (optional)

Secrets can be provided via either env vars (e.g. `GITHUB_TOKEN`) or Docker-secret style files (e.g. `GITHUB_TOKEN_FILE=/run/secrets/github_token`).

### Behavior
- If cache is fresh (7 days), it reuses cached raw data and still records a new
  metrics snapshot.
- If cache is stale, it refetches raw data and updates the cache.

## `scripts/test_api.py`
Quickly probes the API and prints status + JSON previews.

### Usage
```bash
poetry run python test_api.py --owner <org> --repo <name>
```

### Options
- `--base-url` (default: `http://localhost:8000`)
- `--owner` (or set `API_OWNER` in `.env`)
- `--repo` (or set `API_REPO` in `.env`)
- `--limit` (default: 3)

### Notes
- Uses `API_KEY` from `.env` and sends `Authorization: Bearer <API_KEY>`.
- Continues after errors and reports per-endpoint status.

## `scripts/summarize.py`
Generates LLM summaries and stores them via the API.

### Usage
```bash
poetry run python summarize.py --repo <owner>/<repo>
poetry run python summarize.py --owner <owner>
```

### Options
- `--force` to override drift/age checks
- `--history` number of runs in time series (default: 5)
- `--max-age-days` to refresh older summaries (default: 30)
- `--model` (default: `gpt-4o-mini`)
- `--base-url` (default: `http://localhost:8000`)

### Env
- `OPENAI_API_KEY`
- `API_KEY`
- `GITHUB_TOKEN` (for repo descriptions)
