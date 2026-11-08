import os
import time
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from evidence_ai.collection import CollectedPage, fetch_supplied_page, supplied_urls
from evidence_ai.db import SessionLocal
from evidence_ai.discovery import discover_product_sources
from evidence_ai.generation import generate_draft_suggestions
from evidence_ai.models import AutofillJob, CollectedSource, EvidenceSuggestion, GenerationAttempt


logger = logging.getLogger(__name__)


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

        pages: list[CollectedPage] = []
        warnings: list[str] = []
        with httpx.Client(timeout=10.0) as client:
            for url in supplied_urls(job.context):
                page, warning = fetch_supplied_page(url, client)
                if page:
                    pages.append(page)
                if warning:
                    warnings.append(warning)
            discovered, discovery_warnings = discover_product_sources(
                job.product_name, job.context.get("organization_name"), client
            )
        warnings.extend(discovery_warnings)
        pages.extend(
            CollectedPage(item.url, item.title, item.excerpt, "discovered", item.provider)
            for item in discovered
        )
        with httpx.Client(timeout=30.0) as client:
            generation = generate_draft_suggestions(
                pages, job.requested_indicators, client
            )
        warnings.extend(generation.warnings)
        logger.info("Job %s generation outcome: %s", job.id, generation.outcome)
        session.add_all(
            CollectedSource(
                job_id=job.id,
                url=page.url,
                source_type=page.source_type,
                provider=page.provider,
                title=page.title,
                excerpt=page.excerpt,
                fetched_at=page.fetched_at,
            )
            for page in pages
        )
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
        job.status = "completed_with_warnings"
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
            processed = process_next_job()
        except OperationalError:
            logger.exception("Database connection failed; retrying")
            processed = False
        if not processed:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
