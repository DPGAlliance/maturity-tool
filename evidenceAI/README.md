# EvidenceAI

EvidenceAI is the future evidence collection and validation service for DPG
nomination and maturity-assessment workflows.

EvidenceAI currently provides a persistent, authenticated MAT autofill job API
and a worker lifecycle. It does not yet collect, suggest, validate, or score
evidence.

## Local Development

```bash
cp .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d api worker
```

The health endpoint is available at `http://127.0.0.1:8100/health`.

## Documentation

Tracked developer documentation lives in [`docs/`](docs/). Local planning and
scope material lives in `docs/scope/` and is intentionally not tracked.
