import os

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dpg_butler_api.deps import get_db_session, require_api_key
from dpg_butler_api.repo_url_validation import DEFAULT_VIEWER_BASE_URL, build_result_url, validate_repo_url
from dpg_butler_api.schemas import RepoScanJobOut, RepoScanValidateIn, RepoScanValidateOut
from storage.repo_scans import create_repo_scan_job, find_active_repo_scan_job, get_repo_scan_job
from storage.secrets import get_secret


router = APIRouter(prefix="/repo-scans", tags=["repo-scans"], dependencies=[Depends(require_api_key)])


def _viewer_base_url() -> str:
    return os.getenv("VIEWER_BASE_URL", DEFAULT_VIEWER_BASE_URL).rstrip("/")


def _job_out(request: Request, job) -> RepoScanJobOut:
    return RepoScanJobOut(
        scan_id=job.id,
        provider=job.provider,
        host=job.host,
        repo_path=job.repo_path,
        owner=job.owner,
        repo=job.repo,
        repo_url_raw=job.repo_url_raw,
        canonical_repo_url=job.canonical_repo_url,
        status=job.status,
        requested_at=job.requested_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        run_id=job.run_id,
        status_url=str(request.url_for("get_repo_scan_status", scan_id=job.id)),
        result_url=job.result_url,
    )


@router.post("/validate", response_model=RepoScanValidateOut)
def validate_repo_scan(payload: RepoScanValidateIn):
    github_token = get_secret("GITHUB_TOKEN")
    result = validate_repo_url(payload.repo_url, github_token=github_token)
    return RepoScanValidateOut(**result.__dict__)


@router.post("", response_model=RepoScanJobOut)
def create_repo_scan(payload: RepoScanValidateIn, request: Request, session=Depends(get_db_session)):
    github_token = get_secret("GITHUB_TOKEN")
    validation = validate_repo_url(payload.repo_url, github_token=github_token)

    if not validation.valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation.error or "Invalid repository URL")
    if not validation.accessible:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation.error or "Repository is not accessible")
    if not validation.scan_supported or validation.provider != "github" or not validation.owner or not validation.repo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository URL is valid, but ad hoc scanning currently supports GitHub repos only.",
        )

    active_job = find_active_repo_scan_job(
        session,
        provider=validation.provider,
        repo_path=validation.repo_path,
    )
    if active_job is not None:
        if not active_job.result_url:
            active_job.result_url = build_result_url(
                viewer_base_url=_viewer_base_url(),
                provider=active_job.provider,
                repo_path=active_job.repo_path,
                owner=active_job.owner,
                repo=active_job.repo,
                scan_id=active_job.id,
            )
            session.add(active_job)
            session.commit()
            session.refresh(active_job)
        return _job_out(request, active_job)

    placeholder_job = create_repo_scan_job(
        session,
        provider=validation.provider,
        host=validation.host,
        repo_path=validation.repo_path,
        owner=validation.owner,
        repo=validation.repo,
        repo_url_raw=payload.repo_url,
        canonical_repo_url=validation.canonical_repo_url,
        result_url="",
    )
    placeholder_job.result_url = build_result_url(
        viewer_base_url=_viewer_base_url(),
        provider=placeholder_job.provider,
        repo_path=placeholder_job.repo_path,
        owner=placeholder_job.owner,
        repo=placeholder_job.repo,
        scan_id=placeholder_job.id,
    )
    session.add(placeholder_job)
    session.commit()
    session.refresh(placeholder_job)
    return _job_out(request, placeholder_job)


@router.get("/{scan_id}", response_model=RepoScanJobOut, name="get_repo_scan_status")
def get_repo_scan_status(scan_id: int, request: Request, session=Depends(get_db_session)):
    job = get_repo_scan_job(session, scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Repo scan not found")
    return _job_out(request, job)
