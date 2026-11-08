# EvidenceAI

EvidenceAI is the future evidence collection and validation service for DPG
nomination and maturity-assessment workflows.

EvidenceAI provides a persistent, authenticated MAT autofill job API and a
bounded investigation pilot for Source Code Accessibility, Governance, and
Flexible Architecture. It produces citation-backed evidence and capability
drafts only; it does not validate, score, accept, or write back to MAT.

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
