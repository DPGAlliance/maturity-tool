from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, or_, select

from storage.models import RepoScanJob


SCAN_STATUS_PENDING = "pending"
SCAN_STATUS_RUNNING = "running"
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_FAILED = "failed"
SCAN_STATUS_INVALID = "invalid"
ACTIVE_SCAN_STATUSES = (SCAN_STATUS_PENDING, SCAN_STATUS_RUNNING)
SCAN_STAGE_QUEUED = "queued"
SCAN_STAGE_REFRESHING_REPO = "refreshing_repo"
SCAN_STAGE_GENERATING_SUMMARY = "generating_summary"
SCAN_STAGE_COMPLETED = "completed"
SUMMARY_STATUS_NOT_STARTED = "not_started"
SUMMARY_STATUS_RUNNING = "running"
SUMMARY_STATUS_COMPLETED = "completed"
SUMMARY_STATUS_FAILED = "failed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_repo_scan_job(session, scan_id: int) -> RepoScanJob | None:
    return session.get(RepoScanJob, scan_id)


def find_active_repo_scan_job(session, *, provider: str, repo_path: str) -> RepoScanJob | None:
    return session.execute(
        select(RepoScanJob)
        .where(
            RepoScanJob.provider == provider,
            RepoScanJob.repo_path == repo_path,
            RepoScanJob.status.in_(ACTIVE_SCAN_STATUSES),
        )
        .order_by(RepoScanJob.requested_at.desc(), RepoScanJob.id.desc())
    ).scalars().first()


def create_repo_scan_job(
    session,
    *,
    provider: str,
    host: str,
    repo_path: str,
    owner: str | None,
    repo: str | None,
    repo_url_raw: str,
    canonical_repo_url: str,
    result_url: str,
    source: str = "adhoc",
) -> RepoScanJob:
    job = RepoScanJob(
        provider=provider,
        host=host,
        repo_path=repo_path,
        owner=owner,
        repo=repo,
        repo_url_raw=repo_url_raw,
        canonical_repo_url=canonical_repo_url,
        status=SCAN_STATUS_PENDING,
        stage=SCAN_STAGE_QUEUED,
        summary_status=SUMMARY_STATUS_NOT_STARTED,
        result_url=result_url,
        source=source,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_next_pending_repo_scan_job(session) -> dict | None:
    with session.begin():
        job = session.execute(
            select(RepoScanJob)
            .where(RepoScanJob.status == SCAN_STATUS_PENDING)
            .order_by(RepoScanJob.requested_at.asc(), RepoScanJob.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalars().first()
        if job is None:
            return None

        job.status = SCAN_STATUS_RUNNING
        job.stage = SCAN_STAGE_REFRESHING_REPO
        job.started_at = utc_now()
        job.heartbeat_at = utc_now()
        job.finished_at = None
        job.error_message = None
        job.summary_status = SUMMARY_STATUS_NOT_STARTED
        job.summary_error_message = None
        job.summary_finished_at = None
        job.run_id = None
        session.add(job)
        session.flush()
        return {
            "id": job.id,
            "provider": job.provider,
            "host": job.host,
            "repo_path": job.repo_path,
            "owner": job.owner,
            "repo": job.repo,
            "repo_url_raw": job.repo_url_raw,
            "canonical_repo_url": job.canonical_repo_url,
            "result_url": job.result_url,
            "requested_at": job.requested_at,
        }


def record_repo_scan_job_heartbeat(session, job_id: int) -> None:
    job = session.get(RepoScanJob, job_id)
    if job is None or job.status != SCAN_STATUS_RUNNING:
        return
    job.heartbeat_at = utc_now()
    session.add(job)
    session.commit()


def fail_stale_running_repo_scan_jobs(session, *, max_age_seconds: float) -> list[int]:
    cutoff = utc_now() - timedelta(seconds=max_age_seconds)
    jobs = session.execute(
        select(RepoScanJob).where(
            RepoScanJob.status == SCAN_STATUS_RUNNING,
            or_(
                RepoScanJob.heartbeat_at < cutoff,
                and_(RepoScanJob.heartbeat_at.is_(None), RepoScanJob.started_at < cutoff),
            ),
        )
    ).scalars().all()
    for job in jobs:
        job.status = SCAN_STATUS_FAILED
        job.finished_at = utc_now()
        job.error_message = "Worker heartbeat expired before the scan finished."
        session.add(job)
    session.commit()
    return [job.id for job in jobs]


def update_repo_scan_job_stage(
    session,
    job_id: int,
    *,
    stage: str,
    summary_status: str | None = None,
    summary_error_message: str | None = None,
    summary_finished: bool = False,
) -> None:
    job = session.get(RepoScanJob, job_id)
    if job is None:
        return
    job.stage = stage
    if summary_status is not None:
        job.summary_status = summary_status
    if summary_error_message is not None:
        job.summary_error_message = summary_error_message
    if summary_finished:
        job.summary_finished_at = utc_now()
    session.add(job)
    session.commit()


def mark_repo_scan_job_completed(session, job_id: int, *, run_id: int | None = None) -> None:
    job = session.get(RepoScanJob, job_id)
    if job is None:
        return
    job.status = SCAN_STATUS_COMPLETED
    job.stage = SCAN_STAGE_COMPLETED
    job.finished_at = utc_now()
    job.error_message = None
    job.run_id = run_id
    session.add(job)
    session.commit()


def mark_repo_scan_job_failed(session, job_id: int, *, error_message: str) -> None:
    job = session.get(RepoScanJob, job_id)
    if job is None:
        return
    job.status = SCAN_STATUS_FAILED
    job.finished_at = utc_now()
    job.error_message = error_message
    session.add(job)
    session.commit()
