import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from evidence_ai.auth import require_api_key
from evidence_ai.db import get_db_session
from evidence_ai.models import AutofillJob
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


def _request_fingerprint(payload: AutofillJobCreateIn) -> str:
    serialized = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _status_out(job: AutofillJob) -> AutofillJobStatusOut:
    return AutofillJobStatusOut(
        job_id=job.id,
        product_id=job.product_id,
        assessment_id=job.assessment_id,
        status=job.status,
        stage=job.stage,
        created_at=job.created_at,
        updated_at=job.updated_at,
        warnings=job.warnings,
        result=job.result,
        error_code=job.error_code,
        error_message=job.error_message,
    )


@router.post("", response_model=AutofillJobCreatedOut, status_code=status.HTTP_202_ACCEPTED)
def create_autofill_job(
    payload: AutofillJobCreateIn,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_db_session),
) -> AutofillJobCreatedOut:
    fingerprint = _request_fingerprint(payload)
    if idempotency_key:
        existing = session.scalar(
            select(AutofillJob).where(AutofillJob.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key was already used with a different request",
                )
            job = existing
        else:
            job = AutofillJob(
                product_id=payload.product_id,
                assessment_id=payload.assessment_id,
                product_name=payload.product_name,
                product_version=payload.product_version,
                context=payload.context.model_dump(mode="json"),
                requested_indicators=payload.requested_indicators,
                request_fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )
            session.add(job)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                job = session.scalar(
                    select(AutofillJob).where(AutofillJob.idempotency_key == idempotency_key)
                )
                if not job or job.request_fingerprint != fingerprint:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key was already used with a different request",
                    )
    else:
        job = AutofillJob(
            product_id=payload.product_id,
            assessment_id=payload.assessment_id,
            product_name=payload.product_name,
            product_version=payload.product_version,
            context=payload.context.model_dump(mode="json"),
            requested_indicators=payload.requested_indicators,
            request_fingerprint=fingerprint,
        )
        session.add(job)
        session.commit()

    session.refresh(job)
    return AutofillJobCreatedOut(
        job_id=job.id,
        product_id=job.product_id,
        assessment_id=job.assessment_id,
        status=job.status,
        stage=job.stage,
        status_url=str(request.url_for("get_autofill_job", job_id=job.id)),
    )


@router.get("/{job_id}", response_model=AutofillJobStatusOut, name="get_autofill_job")
def get_autofill_job(job_id: UUID, session: Session = Depends(get_db_session)) -> AutofillJobStatusOut:
    job = session.get(AutofillJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Autofill job not found")
    return _status_out(job)
