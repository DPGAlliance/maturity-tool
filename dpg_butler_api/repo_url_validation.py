from urllib.parse import urlencode

# Re-export the provider-registry data structures and validation entrypoint.
from dpg_butler_api.repo_url_providers import RepoUrlCandidate, RepoUrlValidationResult, parse_raw_repo_url, validate_repo_url


DEFAULT_VIEWER_BASE_URL = "http://localhost:8501"


def build_result_url(
    *,
    viewer_base_url: str,
    provider: str,
    repo_path: str,
    scan_id: int,
    owner: str | None = None,
    repo: str | None = None,
) -> str:
    params = {
        "provider": provider,
        "repo_path": repo_path,
        "scan_id": str(scan_id),
    }
    if owner:
        params["owner"] = owner
    if repo:
        params["repo"] = repo
    return f"{viewer_base_url.rstrip('/')}?{urlencode(params)}"
