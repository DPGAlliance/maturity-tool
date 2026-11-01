from storage.models import RepoScanRequestLog


def create_repo_scan_request_log(
    session,
    *,
    source_endpoint: str,
    repo_url_raw: str,
    normalized_host: str | None,
    provider_detected: str | None,
    provider_family: str | None,
    repo_path: str | None,
    canonical_repo_url: str | None,
    valid: bool,
    accessible: bool,
    scan_supported: bool,
    confidence: str | None,
    result_class: str,
    error_message: str | None,
    created_scan_job_id: int | None = None,
) -> RepoScanRequestLog:
    log = RepoScanRequestLog(
        source_endpoint=source_endpoint,
        repo_url_raw=repo_url_raw,
        normalized_host=normalized_host,
        provider_detected=provider_detected,
        provider_family=provider_family,
        repo_path=repo_path,
        canonical_repo_url=canonical_repo_url,
        valid=valid,
        accessible=accessible,
        scan_supported=scan_supported,
        confidence=confidence,
        result_class=result_class,
        error_message=error_message,
        created_scan_job_id=created_scan_job_id,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    return log
