# Scripts

## Make targets
Use the repo `Makefile` for the common Docker Compose flows:

```bash
make build
make build-no-cache
make up
make up-all
make down
make ps
make logs
make refresh-requirements
```

These targets build by Compose service name, so they automatically use the per-service Dockerfiles defined in `docker-compose.yml`.

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

In Docker Compose, this is the `scheduler` profile (`refresh_scheduler` service). Start it early on servers so caches and summaries populate quickly.

### Env
- `REFRESH_OWNERS=owner1,owner2` (but it is recommended to leave unset; falls back to full `DISTINGUISHED_OWNERS` list if unset)
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

Summaries require `API_KEY` (or `API_KEY_FILE`) and `OPENAI_API_KEY` (or `OPENAI_API_KEY_FILE`).

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

Docker (reads API key from secrets file):
```bash
docker compose exec api sh -lc 'API_KEY="$(cat /run/secrets/api_key)" python scripts/test_api.py --owner <org> --repo <name> --base-url http://api:8000'
```

### Options
- `--base-url` (default: `http://localhost:8000`)
- `--owner` (or set `API_OWNER` in `.env`)
- `--repo` (or set `API_REPO` in `.env`)
- `--limit` (default: 3)

### Notes
- Uses `API_KEY` from `.env` and sends `Authorization: Bearer <API_KEY>`.
- Continues after errors and reports per-endpoint status.

## `scripts/db_checks.py`
Runs basic database checks and ad hoc SQL against the Postgres database.

### Usage
Short inline query:
```bash
docker compose exec api python scripts/db_checks.py --sql "select * from runs limit 5"
```

Saved query file:
```bash
docker compose exec api python scripts/db_checks.py --sql-file queries/repos_per_owner.sql
```

Saved query file as CSV:
```bash
docker compose exec api python scripts/db_checks.py --sql-file queries/repos_per_owner.sql --format csv
```

Saved query file as Markdown:
```bash
docker compose exec api python scripts/db_checks.py --sql-file queries/repos_per_owner.sql --format markdown
```

Multiple saved query files:
```bash
docker compose exec api python scripts/db_checks.py \
  --sql-file queries/repos_per_owner.sql \
  --sql-file queries/top_active_repos_per_owner.sql
```

Read SQL from stdin:
```bash
docker compose exec -T api python scripts/db_checks.py --sql-file - <<'SQL'
SELECT owner, COUNT(*) AS repo_count
FROM repos
GROUP BY owner
ORDER BY repo_count DESC, owner;
SQL
```

### Saved queries
- `queries/repos_per_owner.sql`
- `queries/top_active_repos_per_owner.sql`

Edit `top_n` and the time window in `queries/top_active_repos_per_owner.sql` as needed.

### Output formats
- `--format tsv` for tab-separated output (default)
- `--format csv` for spreadsheets and CSV export
- `--format markdown` for GitHub-flavored tables

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

## `scripts/refresh_requirements.sh`
Exports per-service requirements from Poetry.

### Usage
```bash
./scripts/refresh_requirements.sh
```

Equivalent Make target:
```bash
make refresh-requirements
```

### Notes
- Requires Poetry and the `poetry-plugin-export` plugin.
- Writes:
  - `dpg_butler_api/requirements.txt`
  - `data_viewer/requirements.txt`
  - `scripts/requirements.txt`
