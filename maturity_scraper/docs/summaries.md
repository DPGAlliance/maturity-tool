# Summaries

This workflow generates LLM summaries for repos and orgs and stores them in the database.

## Prompt files
- `prompts/repo_summary.md`
- `prompts/org_summary.md`

Each prompt includes a `Prompt-Version` header so outputs can be traced to a prompt revision.

## Script
`scripts/summarize.py`

### Examples
```bash
poetry run python summarize.py --repo egovernments/DIGIT-OSS
poetry run python summarize.py --owner egovernments
```

### Summary write policy
Summaries are written if any of the following is true:
- no previous summary exists
- metrics drift exceeds thresholds
- summary age >= 30 days
- `--force` is provided

## Prompt testing
For fast org prompt iteration without rerunning repo summaries, use:

`scripts/test_org_summary_prompt.py`

It reads the latest stored repo metrics via the API, runs owner-scoped SQL queries from `queries/` to inject authoritative repo count and recent activity rankings, calls `summarize_org()` directly, and does not store unless `--store` is provided.

### Examples
Host:
```bash
poetry run python scripts/test_org_summary_prompt.py --owner <org> --base-url http://localhost:8000 --force
```

Docker:
```bash
docker compose --profile scheduler run --rm refresh_scheduler \
  python scripts/test_org_summary_prompt.py \
  --owner <org> \
  --base-url http://api:8000 \
  --force
```

Store intentionally:
```bash
poetry run python scripts/test_org_summary_prompt.py --owner <org> --base-url http://localhost:8000 --force --store
```

Useful knobs:
- `--top-n` controls how many top active repos to inject (default: `10`)

## Env vars
- `OPENAI_API_KEY`
- `API_KEY`
- `GITHUB_TOKEN` (for repo descriptions)

## Repo description overrides
Optional overrides live in `prompts/repo_overrides.json`.
Example:
```json
{
  "egovernments/DIGIT-OSS": {
    "description": "Core digital governance platform",
    "topics": ["governance", "digit"]
  }
}
```
