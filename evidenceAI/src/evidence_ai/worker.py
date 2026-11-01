import os
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from evidence_ai.collection import CollectedPage, fetch_supplied_page, supplied_urls
from evidence_ai.db import SessionLocal
from evidence_ai.discovery import discover_product_sources
from evidence_ai.models import AutofillJob, CollectedSource


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
        job.status = "completed_with_warnings"
        job.stage = "completed"
        job.heartbeat_at = datetime.now(timezone.utc)
        warnings.append("Suggestions are not generated until the MAT field registry is configured.")
        job.warnings = warnings
        job.result = {
            "sources": [{"url": page.url, "source_type": page.source_type} for page in pages],
            "suggestions": [],
        }
        session.commit()
        return True


def run_worker() -> None:
    poll_seconds = float(os.getenv("EVIDENCE_AI_WORKER_POLL_SECONDS", "5"))
    while True:
        if not process_next_job():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
