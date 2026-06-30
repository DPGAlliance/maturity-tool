# API

This API serves cached metrics and summaries from the database.

## Auth
Use an API key in the Authorization header:

```bash
Authorization: Bearer <API_KEY>
```

Set `API_KEY` in `.env`.

Docker secrets are also supported via `API_KEY_FILE=/run/secrets/api_key`.

## Run locally
```bash
poetry -C dpg_butler_api install
poetry -C dpg_butler_api run python -m uvicorn dpg_butler_api.main:app --reload
```

## Run with Docker
```bash
docker compose up -d --build
```

To enable scheduled refreshes and summaries, start the `scheduler` profile too:
```bash
docker compose --profile scheduler up -d --build
```

## Endpoints

### Repos
`GET /repos?owner=<org>`

Returns repos for a given owner.

### Ad hoc repo scans
`POST /repo-scans/validate`

Validate a submitted repository URL, detect the provider, and report whether ad hoc scanning is currently supported for that repo.

`POST /repo-scans`

Create or reuse an ad hoc single-repo scan job. Returns a status URL and a hidden viewer result URL.

`GET /repo-scans/{scan_id}`

Return job status for an ad hoc repo scan (`pending`, `running`, `completed`, `failed`).

### Metrics (latest by default)
`GET /repos/{owner}/{repo}/metrics`

Optional `run_id` query param to fetch a specific run.

### Metrics history
`GET /repos/{owner}/{repo}/metrics/history?limit=20&offset=0`

### Org metrics
`GET /orgs/{owner}/metrics`

Latest metrics for each repo in the org.

### Summaries
`GET /repos/{owner}/{repo}/summary` (latest repo summary)

`GET /repos/{owner}/{repo}/summaries?limit=20&offset=0`

`GET /orgs/{owner}/summary` (latest org summary)

`GET /orgs/{owner}/summaries?limit=20&offset=0`

`POST /repos/{owner}/{repo}/summary`

`POST /orgs/{owner}/summary`

## Notes
- Ad hoc repo scans are processed by the separate `adhoc_scan_worker` service.
- Direct result links reuse the existing viewer page via query params; there is no separate visible navigation for them.
- Heartbeat/stale-job recovery is not implemented yet. If the worker crashes while a job is `running`, that job may need manual reset or retriggering.

## Response shape (nested metrics)
```json
{
  "owner": "org",
  "repo": "name",
  "run": {
    "id": 123,
    "run_started_at": "2026-01-25T12:00:00Z",
    "time_range": "6 months",
    "since_date": "2025-07-25T12:00:00Z"
  },
  "metrics": {
    "commits": {
      "bus_factor": 4,
      "hhi": 1620,
      "new_contributors": 8
    },
    "issues": {
      "issue_closure_ratio_90d": 0.67
    }
  }
}
```
