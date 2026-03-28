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
