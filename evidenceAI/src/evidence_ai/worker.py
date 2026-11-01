import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from evidence_ai.db import SessionLocal
from evidence_ai.models import AutofillJob


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

        # Collection and suggestion generation land in later slices. Do not emit
        # fabricated sources or answer values while those capabilities are absent.
        job.status = "completed_with_warnings"
        job.stage = "completed"
        job.heartbeat_at = datetime.now(timezone.utc)
        job.warnings = ["Source collection is not enabled yet; no suggestions were generated."]
        job.result = {"suggestions": []}
        session.commit()
        return True


def run_worker() -> None:
    poll_seconds = float(os.getenv("EVIDENCE_AI_WORKER_POLL_SECONDS", "5"))
    while True:
        if not process_next_job():
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
