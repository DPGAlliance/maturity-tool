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
- `--time-range` : Metrics window; one of `6 months`, `1 year`, `2 years`, `3 years`, `all`.
- `--no-full-history` : Limit raw entity fetches to the selected time range.
- `--force-refresh` : Ignore cache age and refetch.

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
