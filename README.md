This is a monorepo with two python packages:
- maturity_tools: A package with tools to assess data maturity.
- data_viewer: A package with tools to visualize the results of data maturity assessment.

They are separate to allow maturity_tools to be used as a dependency in other projects without bringing in streamlit and other visualization dependencies.


They will both have their own README files.

## Docker (recommended)

This repo can be run as a small stack (Postgres + API + Streamlit viewer) via Docker Compose.

### Prereqs
- Docker + Docker Compose
- Secret files (not committed): see [secrets/README.md](secrets/README.md)

### Start
```bash
docker compose up -d --build
```

### URLs
- Viewer: http://localhost:8501
- API docs: http://localhost:8000/docs

### Optional: refresh scheduler (no cron)
The refresh loop is disabled by default.
```bash
docker compose --profile scheduler up -d
```

### Configuration
- Database:
    - `POSTGRES_DB` (default: `maturity`)
    - `POSTGRES_USER` (default: `maturity`)
    - `POSTGRES_PASSWORD` (default: `maturity`)
- Scheduler (profile `scheduler` only):
    - `REFRESH_OWNERS=owner1,owner2` (recommended)
    - `REFRESH_REPO` (optional, single repo name)
    - `REFRESH_INTERVAL_SECONDS` (default: `21600` = 6 hours)
    - `FORCE_REFRESH` (default: `false`)

### Storage (new)
- Local cache + metrics snapshots live under `storage/` using SQLite by default.
- `DATABASE_URL` can point at Postgres (SQLAlchemy + psycopg).
- Refresh cache/metrics: `python scripts/refresh_cache.py --owner <org>`

### Docs
- MkDocs site lives in `docs/` with config in `mkdocs.yml`.
- Storage/cache docs: `docs/storage.md`.
- API docs: `docs/api.md`.