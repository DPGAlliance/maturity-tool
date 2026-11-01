# EvidenceAI

EvidenceAI is the future evidence collection and validation service for DPG
nomination and maturity-assessment workflows.

This initial package is intentionally a scaffold. It provides an independent
FastAPI API, PostgreSQL storage service, and Alembic migration foundation, but it
does not yet collect, suggest, validate, or score evidence.

## Local Development

```bash
cp .env.example .env
docker compose up --build
```

The health endpoint is available at `http://127.0.0.1:8100/health`.

## Scope Documents

- [`docs/dpg-evidence-automation-feasibility-brief.md`](docs/dpg-evidence-automation-feasibility-brief.md)
- [`docs/dpg-nomination-form-autofill-proposal.md`](docs/dpg-nomination-form-autofill-proposal.md)
- [`docs/maturity-assessment-form-autofill-proposal.md`](docs/maturity-assessment-form-autofill-proposal.md)
- [`docs/dpg-nomination-and-maturity-assessment-overlap.md`](docs/dpg-nomination-and-maturity-assessment-overlap.md)
