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

The API creates a persistent asynchronous job. The current worker records a
completed warning and no suggestions until source collection is implemented.

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

## Current Job Lifecycle

Jobs persist in PostgreSQL and are claimed by the worker using row locking. The
current worker returns `completed_with_warnings` and an empty `suggestions`
result. It does not collect sources, call an LLM, or write anything to MAT.

Run database migrations before starting the API or worker:

```bash
docker compose run --rm api alembic upgrade head
```
