import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import select

from maturity_tools.github_call import GitHubRateLimitError
from storage.db import get_session, init_db
from storage.logging_config import configure_logging
from storage.models import Repo, Run
from storage.repo_scans import (
    SCAN_STAGE_GENERATING_SUMMARY,
    claim_next_pending_repo_scan_job,
    fail_stale_running_repo_scan_jobs,
    mark_repo_scan_job_completed,
    mark_repo_scan_job_failed,
    record_repo_scan_job_heartbeat,
    SUMMARY_STATUS_COMPLETED,
    SUMMARY_STATUS_FAILED,
    SUMMARY_STATUS_RUNNING,
    update_repo_scan_job_stage,
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


def _generate_repo_summary(
    *,
    owner: str,
    repo: str,
    api_key: str,
    openai_key: str,
    github_token: str | None,
    base_url: str,
    model: str,
    history_limit: int,
    max_age_days: int,
) -> None:
    import summarize

    summary_session = requests.Session()
    summary_session.headers.update(summarize.api_headers(api_key))
    client = OpenAI(api_key=openai_key)
    repo_prompt = os.path.join(summarize.PROMPTS_DIR, "repo_summary.md")
    summarize.summarize_repo(
        summary_session,
        client,
        base_url.rstrip("/"),
        owner,
        repo,
        repo_prompt,
        model,
        history_limit,
        max_age_days,
        True,
        github_token,
        True,
    )


def _heartbeat_loop(job_id: int, stop_event: threading.Event, interval_seconds: float) -> None:
    while not stop_event.wait(interval_seconds):
        session = get_session()
        try:
            record_repo_scan_job_heartbeat(session, job_id)
        except Exception:
            session.rollback()
            logger.exception("Could not record heartbeat for ad hoc scan %s", job_id)
        finally:
            session.close()


def main() -> None:
    configure_logging()
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(repo_root, ".env"))

    token = get_secret("GITHUB_TOKEN", required=True)
    api_key = get_secret("API_KEY", required=True)
    openai_key = get_secret("OPENAI_API_KEY", required=True)
    summary_base_url = os.getenv("SUMMARY_BASE_URL", "http://api:8000")
    summary_model = os.getenv("SUMMARY_MODEL", "gpt-4o-mini")
    summary_history_limit = int(os.getenv("SUMMARY_HISTORY", "5"))
    summary_max_age_days = int(os.getenv("SUMMARY_MAX_AGE_DAYS", "30"))
    poll_seconds = float(os.getenv("ADHOC_SCAN_POLL_SECONDS", "5"))
    heartbeat_seconds = float(os.getenv("ADHOC_SCAN_HEARTBEAT_SECONDS", "60"))
    max_running_seconds = float(os.getenv("ADHOC_SCAN_MAX_RUNNING_SECONDS", "7200"))

    init_db()

    import refresh_cache

    logger.info("Starting ad hoc scan worker (poll_seconds=%s)", poll_seconds)
    while True:
        session = get_session()
        try:
            expired_job_ids = fail_stale_running_repo_scan_jobs(
                session,
                max_age_seconds=max_running_seconds,
            )
            if expired_job_ids:
                logger.warning("Marked stale ad hoc scans as failed: %s", expired_job_ids)
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

        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(job["id"], heartbeat_stop, heartbeat_seconds),
            daemon=True,
        )
        heartbeat_thread.start()
        try:
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
                    update_repo_scan_job_stage(
                        session,
                        job["id"],
                        stage=SCAN_STAGE_GENERATING_SUMMARY,
                        summary_status=SUMMARY_STATUS_RUNNING,
                    )
                    try:
                        _generate_repo_summary(
                            owner=owner,
                            repo=repo,
                            api_key=api_key,
                            openai_key=openai_key,
                            github_token=token,
                            base_url=summary_base_url,
                            model=summary_model,
                            history_limit=summary_history_limit,
                            max_age_days=summary_max_age_days,
                        )
                        update_repo_scan_job_stage(
                            session,
                            job["id"],
                            stage=SCAN_STAGE_GENERATING_SUMMARY,
                            summary_status=SUMMARY_STATUS_COMPLETED,
                            summary_error_message="",
                            summary_finished=True,
                        )
                    except Exception as summary_exc:
                        logger.exception(
                            "Ad hoc scan %s summary failed for %s/%s",
                            job["id"],
                            owner,
                            repo,
                        )
                        update_repo_scan_job_stage(
                            session,
                            job["id"],
                            stage=SCAN_STAGE_GENERATING_SUMMARY,
                            summary_status=SUMMARY_STATUS_FAILED,
                            summary_error_message=str(summary_exc),
                            summary_finished=True,
                        )
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
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=heartbeat_seconds + 1)


if __name__ == "__main__":
    main()
