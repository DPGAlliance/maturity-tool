# MAT Autofill API

EvidenceAI is called by the MAT backend only. The browser must not call this API
or receive its bearer token.

## Authentication

Send the configured EvidenceAI API key as a bearer token:

```http
Authorization: Bearer <EVIDENCE_AI_API_KEY>
```

## Create an Autofill Job

`POST /v1/mat/autofill-jobs`

The API creates a persistent asynchronous job. The worker runs a bounded MAT
pilot for Source Code Accessibility, Governance, and Flexible Architecture,
then returns citation-backed AI drafts when OpenAI is configured.

```json
{
  "product_id": "dev-digit-core",
  "assessment_id": "dev-digit-core-assessment-001",
  "product_name": "DIGIT Core",
  "context": {
    "website_url": "https://core.digit.org",
    "repository_url": "https://github.com/egovernments/Digit-Core"
  }
}
```

Use `Idempotency-Key` when retrying a request. Reusing the same key with the
same payload returns the original job. Reusing it with a different payload
returns `409 Conflict`.

## Poll a Job

`GET /v1/mat/autofill-jobs/{job_id}`

Both endpoints return MAT-owned `product_id` and `assessment_id` unchanged.
EvidenceAI's `job_id` identifies the asynchronous collection request.

## Inspect a Job Trace

`GET /v1/mat/autofill-jobs/{job_id}/trace`

The authenticated MAT backend can inspect persisted source excerpts, bounded
investigation actions, and model generation attempts here. Each action records
the model request, validated execution outcome, and details. Attempts include
the raw model output, outcome, and rejection reason so prompts can be improved.
This endpoint is internal-only; do not expose it directly to browsers.

## Current Job Lifecycle

Jobs persist in PostgreSQL and are claimed by the worker using row locking.
Each generated item has `origin: "ai"` and `state: "suggested"`; it is never an
accepted MAT answer. EvidenceAI never writes to MAT. When source collection or
generation cannot run, the job completes with an explicit warning.

Run database migrations before starting the API or worker:

```bash
docker compose run --rm api alembic upgrade head
```
