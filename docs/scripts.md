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

## `scripts/test_cached_api.py`
Quickly probes the cached/read-only API endpoints and prints status + JSON previews.

### Usage
```bash
cd scripts
poetry run python test_cached_api.py --owner <org> --repo <name>
```

Docker:
```bash
docker compose exec api python scripts/test_cached_api.py --owner <org> --repo <name> --base-url http://localhost:8000
```

### Options
- `--base-url` (default: `http://localhost:8000`)
- `--owner` (or set `API_OWNER` in `.env`)
- `--repo` (or set `API_REPO` in `.env`)
- `--limit` (default: 3)

### Notes
- Reads the API key from `API_KEY`, `API_KEY_FILE`, or local `secrets/api_key`.
- Continues after errors and reports per-endpoint status.

## `scripts/test_repo_scan_api.py`
Tests the ad hoc single-repo scan API flow.

### Usage
With a full repo URL:
```bash
cd scripts
poetry run python test_repo_scan_api.py --repo-url https://github.com/egovernments/DIGIT-OSS
```

Or construct the GitHub URL from owner/repo:
```bash
cd scripts
poetry run python test_repo_scan_api.py --owner egovernments --repo DIGIT-OSS
```

Wait for completion with visible progress:
```bash
cd scripts
poetry run python test_repo_scan_api.py --owner egovernments --repo DIGIT-OSS --wait-for-scan
```

Docker:
```bash
docker compose exec api python scripts/test_repo_scan_api.py --owner egovernments --repo DIGIT-OSS --base-url http://localhost:8000
```

### Options
- `--base-url` (default: `http://localhost:8000`)
- `--repo-url` full repository URL to validate and scan
- `--owner` and `--repo` to build a GitHub repo URL when `--repo-url` is omitted
- `--wait-for-scan` to keep polling until the scan is `completed` or `failed`
- `--poll-seconds` (default: 5)
- `--timeout-seconds` (default: 300)

### Notes
- Reads the API key from `API_KEY`, `API_KEY_FILE`, or local `secrets/api_key`.
- Prints the immediate `scan_id`, `status_url`, and `result_url` after creation.
- `--wait-for-scan` is not silent: it prints visible status progress while polling.

## `scripts/test_repo_validation_api.py`
Focused tester for provider-aware repo validation and optional scan creation.

Use this when working on supported hosts, unsupported hosts, forge-family inference, and validation telemetry.

### Usage
Single URL:
```bash
cd scripts
poetry run python test_repo_validation_api.py --repo-url https://github.com/egovernments/DIGIT-OSS --show-summary
```

Built-in scenario from the shared case file:
```bash
cd scripts
poetry run python test_repo_validation_api.py --scenario github --show-summary
```

Batch file:
```bash
cd scripts
poetry run python test_repo_validation_api.py --file urls.txt --show-summary
```

Also create scans for supported repos:
```bash
cd scripts
poetry run python test_repo_validation_api.py --file urls.txt --create-scan --show-summary
```

### Notes
- Reads the API key from `API_KEY`, `API_KEY_FILE`, or local `secrets/api_key`.
- Uses `scripts/repo_validation_cases.json` by default for scenario-driven testing.
- Prints provider, family, confidence, accessibility, support, and `result_class` for each tested URL.
- Compares actual responses against expected outcomes and prints `PASS` / `FAIL` per case.
- `--strict` exits non-zero if any case fails its expected result.
- This is the main script to tweak when testing expanded repo-provider validation behavior.

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
- `queries/repo_scan_request_counts_by_provider.sql`
- `queries/repo_scan_request_counts_by_result.sql`
- `queries/repo_scan_request_top_hosts.sql`
- `queries/repo_scan_request_validate_to_create_conversion.sql`
- `queries/repo_scan_request_recent_requests.sql`

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

## `scripts/locaiton/collect_contributor_locations.py`
Experimental contributor location collector for one owner or repo scope.

It reads contributor logins from the cached database, enriches them from GitHub user profiles, and optionally geocodes profile `location` strings into country/city data.

### Example
```bash
cd scripts
poetry run python locaiton/collect_contributor_locations.py --owner egovernments
```

Repo scope:
```bash
cd scripts
poetry run python locaiton/collect_contributor_locations.py --owner egovernments --repo DIGIT-OSS
```

### Outputs
Written under `.cache/location/<scope>/` by default:
- `contributors.csv`
- `contributors.json`
- `country_summary.csv`
- `city_summary.csv`
- `summary.json`

Cached fetches are stored under `.cache/location/caches/`.

## `scripts/collect_repo_practice_signals.py`
Experimental GitHub-signal collector for repository practices.

It evaluates these booleans per repo:
- `has_security_policy`
- `has_governance`
- `has_code_of_conduct`
- `has_containerization`

The script uses:
- `GET /repos/{owner}/{repo}`
- `GET /repos/{owner}/{repo}/community/profile`
- `GET /repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1`

Governance and containerization evidence are split into strong and medium signals in the output.

### Example
```bash
cd scripts
poetry run python collect_repo_practice_signals.py --owner egovernments
```

Single repo:
```bash
cd scripts
poetry run python collect_repo_practice_signals.py --owner egovernments --repo DIGIT-OSS
```

### Outputs
Written under `.cache/repo_practice_signals/<scope>/` by default:
- `repo_practice_signals.csv`
- `repo_practice_signals.json`
- `summary.json`

Cached GitHub responses are stored under `.cache/repo_practice_signals/caches/`.

## `scripts/adhoc_scan_worker.py`
Background worker for API-created ad hoc single-repo scans.

It polls the database for `pending` repo scan jobs, claims one with DB locking, runs the existing cache refresh for that repo with `force_refresh=True`, and marks the job as `completed` or `failed`.

### Notes
- Intended to run via the `adhoc_scan_worker` Docker service.
- The worker currently has no stale-running heartbeat recovery. If it crashes while a job is `running`, that job may need manual reset or retriggering.

Per-repo output includes `scan_status` so blocked or failed repos are recorded without aborting the full owner scan.

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
