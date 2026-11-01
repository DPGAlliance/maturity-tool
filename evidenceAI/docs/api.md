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

The API currently creates an asynchronous queued job. It does not yet collect
sources or create suggestions.

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

Use `Idempotency-Key` when retrying a request. Reusing the same key returns the
same queued job during this development-only in-memory phase.

## Poll a Job

`GET /v1/mat/autofill-jobs/{job_id}`

Both endpoints return MAT-owned `product_id` and `assessment_id` unchanged.
EvidenceAI's `job_id` identifies the asynchronous collection request.

## Development Limitations

Jobs are stored in memory in this first API-contract slice. Restarting the API
removes them. The next implementation slice adds PostgreSQL persistence and a
worker.
