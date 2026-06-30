import logging
import os
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import select

from maturity_tools.github_call import GitHubRateLimitError
from storage.db import get_session, init_db
from storage.logging_config import configure_logging
from storage.models import Repo, Run
from storage.repo_scans import (
    claim_next_pending_repo_scan_job,
    mark_repo_scan_job_completed,
    mark_repo_scan_job_failed,
)
from storage.secrets import get_secret


logger = logging.getLogger("adhoc_scan_worker")


def _format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes or hours:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _latest_run_id(session, owner: str, repo: str) -> int | None:
    repo_obj = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == repo)
    ).scalar_one_or_none()
    if repo_obj is None:
        return None
    return session.execute(
        select(Run.id)
        .where(Run.repo_id == repo_obj.id)
        .order_by(Run.run_started_at.desc(), Run.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _sleep_for_rate_limit(exc: GitHubRateLimitError, *, owner: str, repo: str) -> None:
    sleep_seconds = exc.sleep_seconds()
    reset_at = exc.reset_at.isoformat() if exc.reset_at else None
    logger.warning(
        "GitHub rate limit paused ad hoc scan for %s/%s at stage=%s; sleeping %s until %s",
        owner,
        repo,
        exc.request_name or "unknown",
        _format_duration(sleep_seconds),
        reset_at,
    )
    time.sleep(sleep_seconds)


def main() -> None:
    configure_logging()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(repo_root, ".env"))

    token = get_secret("GITHUB_TOKEN", required=True)
    poll_seconds = float(os.getenv("ADHOC_SCAN_POLL_SECONDS", "5"))

    init_db()

    import refresh_cache

    logger.info("Starting ad hoc scan worker (poll_seconds=%s)", poll_seconds)
    while True:
        session = get_session()
        try:
            job = claim_next_pending_repo_scan_job(session)
        finally:
            session.close()

        if job is None:
            time.sleep(poll_seconds)
            continue

        if job["provider"] != "github" or not job.get("owner") or not job.get("repo"):
            session = get_session()
            try:
                mark_repo_scan_job_failed(
                    session,
                    job["id"],
                    error_message="Ad hoc scanning currently supports GitHub owner/repo targets only.",
                )
            finally:
                session.close()
            continue

        owner = job["owner"]
        repo = job["repo"]
        logger.info("Processing ad hoc scan %s for %s/%s", job["id"], owner, repo)

        while True:
            session = get_session()
            try:
                refresh_cache.collect_for_repo(
                    session=session,
                    owner=owner,
                    repo=repo,
                    token=token,
                    force_refresh=True,
                )
                run_id = _latest_run_id(session, owner, repo)
                mark_repo_scan_job_completed(session, job["id"], run_id=run_id)
                logger.info("Ad hoc scan %s completed for %s/%s (run_id=%s)", job["id"], owner, repo, run_id)
                break
            except GitHubRateLimitError as exc:
                session.rollback()
                session.close()
                _sleep_for_rate_limit(exc, owner=owner, repo=repo)
                continue
            except Exception as exc:
                session.rollback()
                session.close()
                logger.exception("Ad hoc scan %s failed for %s/%s", job["id"], owner, repo)
                failure_session = get_session()
                try:
                    mark_repo_scan_job_failed(failure_session, job["id"], error_message=str(exc))
                finally:
                    failure_session.close()
                break
            finally:
                if session.is_active:
                    session.close()


if __name__ == "__main__":
    main()
