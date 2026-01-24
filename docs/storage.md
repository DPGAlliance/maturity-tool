# Storage Module

The storage module provides a lightweight persistence layer for:
- Raw GitHub data (commits, issues, PRs, releases, branches).
- Metrics snapshots recorded over time.

The implementation is intentionally isolated under `storage/` so it can be
replaced or moved later without tight coupling to the app or analyzers.

## Layout
- `storage/db.py` : SQLAlchemy engine + session + init helper.
- `storage/models.py` : ORM models for repos, runs, raw entities, metrics.
- `storage/cache.py` : upserts, cache freshness, and basic read helpers.
- `storage/metrics.py` : helper to store metrics as key/value records.

## Database URL
- Default SQLite file: `storage/maturity.db`.
- Override with `DATABASE_URL` (Postgres-compatible).
- `.env` is auto-loaded by the app and refresh script.

## Cache Policy
- Each repo + entity type records `fetched_at` in `fetch_log`.
- If data is older than 7 days, a refresh is triggered.
- Use `--force-refresh` in scripts to override.

## Metrics Snapshots
- Each refresh creates a new `runs` record.
- Metrics are stored in `metrics` with `(run_id, scope, name)` uniqueness.
- This preserves history over time and supports trend analysis.

## Streamlit Switch
- The app reads `USE_DB_CACHE` and exposes a toggle.
- When off, the app behaves exactly as before.
- When on, cached data is used if fresh; otherwise it refetches and updates.
