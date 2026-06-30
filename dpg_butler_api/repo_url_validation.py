from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import requests


DEFAULT_VIEWER_BASE_URL = "http://localhost:8501"
GITHUB_API_ROOT = "https://api.github.com"


@dataclass
class RepoUrlCandidate:
    provider: str
    host: str
    repo_path: str
    canonical_repo_url: str
    owner: str | None
    repo: str | None


@dataclass
class RepoUrlValidationResult:
    valid: bool
    provider: str | None
    host: str | None
    repo_path: str | None
    owner: str | None
    repo: str | None
    canonical_repo_url: str | None
    accessible: bool
    scan_supported: bool
    default_branch: str | None
    archived: bool | None
    visibility: str | None
    error: str | None


def _normalize_host(host: str) -> str:
    return host.lower().strip()


def _split_segments(path: str) -> list[str]:
    cleaned = path.strip().strip("/")
    if not cleaned:
        return []
    segments = [segment for segment in cleaned.split("/") if segment]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][:-4]
    return segments


def _parse_github_candidate(host: str, segments: list[str]) -> RepoUrlCandidate | None:
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1]
    repo_path = f"{owner}/{repo}"
    return RepoUrlCandidate(
        provider="github",
        host=host,
        repo_path=repo_path,
        owner=owner,
        repo=repo,
        canonical_repo_url=f"https://{host}/{repo_path}",
    )


def _parse_gitlab_candidate(host: str, segments: list[str]) -> RepoUrlCandidate | None:
    if "-" in segments:
        repo_segments = segments[: segments.index("-")]
    else:
        repo_segments = segments
    if len(repo_segments) < 2:
        return None
    repo_path = "/".join(repo_segments)
    return RepoUrlCandidate(
        provider="gitlab",
        host=host,
        repo_path=repo_path,
        owner=None,
        repo=repo_segments[-1],
        canonical_repo_url=f"https://{host}/{repo_path}",
    )


def _parse_bitbucket_candidate(host: str, segments: list[str]) -> RepoUrlCandidate | None:
    if len(segments) < 2:
        return None
    workspace, repo = segments[0], segments[1]
    repo_path = f"{workspace}/{repo}"
    return RepoUrlCandidate(
        provider="bitbucket",
        host=host,
        repo_path=repo_path,
        owner=workspace,
        repo=repo,
        canonical_repo_url=f"https://{host}/{repo_path}",
    )


def parse_repo_url(raw_url: str) -> RepoUrlCandidate | None:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    host = _normalize_host(parsed.netloc)
    if host.startswith("www."):
        host = host[4:]

    segments = _split_segments(parsed.path)
    if host == "github.com":
        return _parse_github_candidate(host, segments)
    if host == "gitlab.com":
        return _parse_gitlab_candidate(host, segments)
    if host == "bitbucket.org":
        return _parse_bitbucket_candidate(host, segments)
    return None


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "maturity-tool-repo-scan-api",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_repo_blocked(response: requests.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    message = str(payload.get("message") or "")
    block = payload.get("block") or {}
    if response.status_code == 403 and ("repository access blocked" in message.lower() or block):
        reason = block.get("reason")
        return f"Repository access blocked{f': {reason}' if reason else ''}"
    return None


def validate_repo_url(raw_url: str, *, github_token: str | None = None, request_timeout: float = 20.0) -> RepoUrlValidationResult:
    candidate = parse_repo_url(raw_url)
    if candidate is None:
        return RepoUrlValidationResult(
            valid=False,
            provider=None,
            host=None,
            repo_path=None,
            owner=None,
            repo=None,
            canonical_repo_url=None,
            accessible=False,
            scan_supported=False,
            default_branch=None,
            archived=None,
            visibility=None,
            error="Unsupported or invalid repository URL.",
        )

    if candidate.provider == "github":
        response = requests.get(
            f"{GITHUB_API_ROOT}/repos/{candidate.owner}/{candidate.repo}",
            headers=_headers(github_token),
            timeout=request_timeout,
        )
        if response.ok:
            payload = response.json()
            owner = (payload.get("owner") or {}).get("login") or candidate.owner
            repo = payload.get("name") or candidate.repo
            repo_path = payload.get("full_name") or f"{owner}/{repo}"
            return RepoUrlValidationResult(
                valid=True,
                provider=candidate.provider,
                host=candidate.host,
                repo_path=repo_path,
                owner=owner,
                repo=repo,
                canonical_repo_url=f"https://{candidate.host}/{repo_path}",
                accessible=True,
                scan_supported=True,
                default_branch=payload.get("default_branch"),
                archived=payload.get("archived"),
                visibility=payload.get("visibility"),
                error=None,
            )

        blocked_error = _github_repo_blocked(response)
        if blocked_error:
            return RepoUrlValidationResult(
                valid=True,
                provider=candidate.provider,
                host=candidate.host,
                repo_path=candidate.repo_path,
                owner=candidate.owner,
                repo=candidate.repo,
                canonical_repo_url=candidate.canonical_repo_url,
                accessible=False,
                scan_supported=True,
                default_branch=None,
                archived=None,
                visibility=None,
                error=blocked_error,
            )

        if response.status_code == 404:
            return RepoUrlValidationResult(
                valid=False,
                provider=candidate.provider,
                host=candidate.host,
                repo_path=candidate.repo_path,
                owner=candidate.owner,
                repo=candidate.repo,
                canonical_repo_url=candidate.canonical_repo_url,
                accessible=False,
                scan_supported=True,
                default_branch=None,
                archived=None,
                visibility=None,
                error="GitHub repository not found.",
            )

        return RepoUrlValidationResult(
            valid=False,
            provider=candidate.provider,
            host=candidate.host,
            repo_path=candidate.repo_path,
            owner=candidate.owner,
            repo=candidate.repo,
            canonical_repo_url=candidate.canonical_repo_url,
            accessible=False,
            scan_supported=True,
            default_branch=None,
            archived=None,
            visibility=None,
            error=f"GitHub validation failed with status {response.status_code}.",
        )

    response = requests.get(
        candidate.canonical_repo_url,
        headers=_headers(),
        allow_redirects=True,
        timeout=request_timeout,
    )
    if response.ok:
        return RepoUrlValidationResult(
            valid=True,
            provider=candidate.provider,
            host=candidate.host,
            repo_path=candidate.repo_path,
            owner=candidate.owner,
            repo=candidate.repo,
            canonical_repo_url=candidate.canonical_repo_url,
            accessible=True,
            scan_supported=False,
            default_branch=None,
            archived=None,
            visibility=None,
            error=None,
        )

    if response.status_code == 404:
        return RepoUrlValidationResult(
            valid=False,
            provider=candidate.provider,
            host=candidate.host,
            repo_path=candidate.repo_path,
            owner=candidate.owner,
            repo=candidate.repo,
            canonical_repo_url=candidate.canonical_repo_url,
            accessible=False,
            scan_supported=False,
            default_branch=None,
            archived=None,
            visibility=None,
            error=f"{candidate.provider.title()} repository not found.",
        )

    return RepoUrlValidationResult(
        valid=True,
        provider=candidate.provider,
        host=candidate.host,
        repo_path=candidate.repo_path,
        owner=candidate.owner,
        repo=candidate.repo,
        canonical_repo_url=candidate.canonical_repo_url,
        accessible=False,
        scan_supported=False,
        default_branch=None,
        archived=None,
        visibility=None,
        error=f"{candidate.provider.title()} repository exists but could not be checked cleanly (status {response.status_code}).",
    )


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
