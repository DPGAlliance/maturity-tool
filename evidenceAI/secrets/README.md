# EvidenceAI Secrets

Docker Compose reads local secret files from this directory. The files themselves
are ignored by Git.

Create these files before running services that require them:

- `evidence_ai_api_key`: bearer token accepted from the MAT backend.
- `openai_api_key`: required when LLM suggestion generation is enabled.
- `brave_search_api_key`: required when live Brave discovery is enabled.

Generate a development API key without printing it:

```bash
openssl rand -hex 32 > secrets/evidence_ai_api_key
```

EvidenceAI starts without `openai_api_key`, but completes collection jobs with a
warning instead of AI draft suggestions.
