from datetime import datetime, timezone
from threading import Lock
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from evidence_ai.auth import require_api_key
from evidence_ai.schemas import (
    AutofillJobCreateIn,
    AutofillJobCreatedOut,
    AutofillJobStatusOut,
)


router = APIRouter(
    prefix="/v1/mat/autofill-jobs",
    tags=["MAT autofill"],
    dependencies=[Depends(require_api_key)],
)


class InMemoryJobStore:
    """Development-only store replaced by persistent jobs in the next slice."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, AutofillJobStatusOut] = {}
        self._idempotency_keys: dict[str, UUID] = {}
        self._lock = Lock()

    def create(self, payload: AutofillJobCreateIn, idempotency_key: str | None) -> AutofillJobStatusOut:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency_keys:
                return self._jobs[self._idempotency_keys[idempotency_key]]

            now = datetime.now(timezone.utc)
            job = AutofillJobStatusOut(
                job_id=uuid4(),
                product_id=payload.product_id,
                assessment_id=payload.assessment_id,
                status="pending",
                stage="queued",
                created_at=now,
                updated_at=now,
            )
            self._jobs[job.job_id] = job
            if idempotency_key:
                self._idempotency_keys[idempotency_key] = job.job_id
            return job

    def get(self, job_id: UUID) -> AutofillJobStatusOut | None:
        with self._lock:
            return self._jobs.get(job_id)


job_store = InMemoryJobStore()


@router.post("", response_model=AutofillJobCreatedOut, status_code=status.HTTP_202_ACCEPTED)
def create_autofill_job(
    payload: AutofillJobCreateIn,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> AutofillJobCreatedOut:
    job = job_store.create(payload, idempotency_key)
    return AutofillJobCreatedOut(
        job_id=job.job_id,
        product_id=job.product_id,
        assessment_id=job.assessment_id,
        status=job.status,
        stage=job.stage,
        status_url=str(request.url_for("get_autofill_job", job_id=job.job_id)),
    )


@router.get("/{job_id}", response_model=AutofillJobStatusOut, name="get_autofill_job")
def get_autofill_job(job_id: UUID) -> AutofillJobStatusOut:
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autofill job not found")
    return job
