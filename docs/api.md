# API

This API serves cached metrics and summaries from the database.

## Auth
Use an API key in the Authorization header:

```bash
Authorization: Bearer <API_KEY>
```

Set `API_KEY` in `.env`.

## Run locally
```bash
uvicorn api.main:app --reload
```

## Endpoints

### Repos
`GET /repos?owner=<org>`

Returns repos for a given owner.

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
