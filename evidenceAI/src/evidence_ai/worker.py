import os
import time
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from evidence_ai.collection import CollectedPage
from evidence_ai.db import SessionLocal
from evidence_ai.generation import generate_draft_suggestions
from evidence_ai.investigation import investigate
from evidence_ai.mat_registry import three_section_pilot_indicators
from evidence_ai.models import AutofillJob, CollectedSource, EvidenceSuggestion, GenerationAttempt, InvestigationAction


logger = logging.getLogger(__name__)
STALE_JOB_SECONDS = 300


def fail_stale_jobs(session_factory: sessionmaker[Session] = SessionLocal) -> int:
    """Make abandoned work visible rather than leaving jobs running forever."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_JOB_SECONDS)
    with session_factory() as session:
        jobs = session.scalars(
            select(AutofillJob).where(
                AutofillJob.status == "running",
                AutofillJob.heartbeat_at < cutoff,
            )
        ).all()
        for job in jobs:
            job.status = "failed"
            job.stage = "failed"
            job.error_code = "worker_heartbeat_timeout"
            job.error_message = "The worker heartbeat expired before this job completed."
            job.heartbeat_at = datetime.now(timezone.utc)
        session.commit()
        return len(jobs)


def process_next_job(session_factory: sessionmaker[Session] = SessionLocal) -> bool:
    """Claim and complete one job without inventing evidence before collection exists."""
    with session_factory() as session:
        job = session.scalar(
            select(AutofillJob)
            .where(AutofillJob.status == "pending")
            .order_by(AutofillJob.created_at)
            .with_for_update(skip_locked=True)
        )
        if not job:
            return False

        logger.info("Claimed autofill job %s", job.id)

        now = datetime.now(timezone.utc)
        job.status = "running"
        job.stage = "preparing_collection"
        job.claimed_at = now
        job.heartbeat_at = now
        job.attempt_count += 1
        session.commit()

        warnings: list[str] = []
        job.stage = "investigating"
        session.commit()
        with httpx.Client(timeout=10.0) as client:
            pages, actions, investigation_warnings = investigate(job.context, job.product_name, client)
        warnings.extend(investigation_warnings)
        session.add_all(
            InvestigationAction(
                job_id=job.id,
                sequence=sequence,
                action=str(action["action"]),
                requested=action["requested"] if isinstance(action.get("requested"), dict) else {},
                outcome=str(action["outcome"]),
                details={key: value for key, value in action.items() if key not in {"action", "requested", "outcome"}},
            )
            for sequence, action in enumerate(actions, start=1)
        )
        session.add_all(
            CollectedSource(job_id=job.id, url=page.url, source_type=page.source_type, provider=page.provider, title=page.title, excerpt=page.excerpt, fetched_at=page.fetched_at, links=page.links or [], is_partial=page.is_partial, fetched_bytes=page.fetched_bytes)
            for page in pages
        )
        job.stage = "generating_drafts"
        job.heartbeat_at = datetime.now(timezone.utc)
        job.result = {"collection": {"fetched_sources": len(pages), "actions": len(actions)}}
        session.commit()
        with httpx.Client(timeout=30.0) as client:
            generation = generate_draft_suggestions(
                pages, three_section_pilot_indicators(), client, job.product_name
            )
        warnings.extend(generation.warnings)
        logger.info("Job %s generation outcome: %s", job.id, generation.outcome)
        session.add(
            GenerationAttempt(
                job_id=job.id,
                model="gpt-6-luna",
                outcome=generation.outcome,
                raw_output=generation.raw_output[:20_000],
                rejection_reason=generation.rejection_reason,
            )
        )
        session.add_all(
            EvidenceSuggestion(
                job_id=job.id,
                indicator_id=suggestion.indicator_id,
                answer=suggestion.answer,
                rationale=suggestion.rationale,
                confidence=suggestion.confidence,
                citations=suggestion.citations,
                suggestion_type=suggestion.suggestion_type,
            )
            for suggestion in generation.suggestions
        )
        job.status = "completed_with_warnings" if warnings else "completed"
        job.stage = "completed"
        job.heartbeat_at = datetime.now(timezone.utc)
        job.warnings = warnings
        job.result = {
            "sources": [{"url": page.url, "source_type": page.source_type} for page in pages],
            "evidence_suggestions": [
                {
                    "indicator_id": suggestion.indicator_id,
                    "answer": suggestion.answer,
                    "rationale": suggestion.rationale,
                    "confidence": suggestion.confidence,
                    "citations": suggestion.citations,
                    "origin": suggestion.origin,
                    "state": suggestion.state,
                }
                for suggestion in generation.suggestions if suggestion.suggestion_type == "evidence"
            ],
            "capability_suggestions": [
                {
                    "indicator_id": suggestion.indicator_id,
                    "answer": suggestion.answer,
                    "rationale": suggestion.rationale,
                    "confidence": suggestion.confidence,
                    "citations": suggestion.citations,
                    "origin": suggestion.origin,
                    "state": suggestion.state,
                }
                for suggestion in generation.suggestions if suggestion.suggestion_type == "capability"
            ],
            "generation_outcome": generation.outcome,
        }
        session.commit()
        return True


def run_worker() -> None:
    poll_seconds = float(os.getenv("EVIDENCE_AI_WORKER_POLL_SECONDS", "5"))
    while True:
        try:
            failed = fail_stale_jobs()
            if failed:
                logger.warning("Marked %s stale autofill job(s) as failed", failed)
            processed = process_next_job()
        except SQLAlchemyError:
            logger.exception("Database operation failed; retrying")
            processed = False
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
