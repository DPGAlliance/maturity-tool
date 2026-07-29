from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable
from urllib.parse import quote, urlparse

import requests


GITHUB_API_ROOT = "https://api.github.com"


@dataclass
class ParsedRepoUrlInput:
    raw_url: str
    scheme: str
    host: str
    path: str
    segments: list[str]


@dataclass
class RepoUrlCandidate:
    provider: str
    family: str
    host: str
    repo_path: str
    canonical_repo_url: str
    owner: str | None
    repo: str | None
    confidence: str


@dataclass
class RepoUrlValidationResult:
    valid: bool
    provider: str | None
    provider_family: str | None
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
    confidence: str | None
    result_class: str
    error: str | None


@dataclass
class ProviderHandler:
    provider: str
    family: str
    scan_supported: bool
    exact_hosts: tuple[str, ...]
    parser: Callable[[str, list[str], str], RepoUrlCandidate | None]
    validator: Callable[[RepoUrlCandidate, str | None, float], RepoUrlValidationResult]
    fingerprint: Callable[[str, float], bool] | None = None


def _normalize_host(host: str) -> str:
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _split_segments(path: str) -> list[str]:
    cleaned = path.strip().strip("/")
    if not cleaned:
        return []
    segments = [segment for segment in cleaned.split("/") if segment]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][:-4]
    return segments


def parse_raw_repo_url(raw_url: str) -> ParsedRepoUrlInput | None:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return ParsedRepoUrlInput(
        raw_url=raw_url.strip(),
        scheme=parsed.scheme,
        host=_normalize_host(parsed.netloc),
        path=parsed.path,
        segments=_split_segments(parsed.path),
    )


def _headers(token: str | None = None, *, accept: str = "application/json") -> dict[str, str]:
    headers = {
        "Accept": accept,
        "User-Agent": "maturity-tool-repo-scan-api",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _response_text(response: requests.Response) -> str:
    return response.text or ""


def _response_json(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        return None


def _result_from_candidate(
    candidate: RepoUrlCandidate,
    *,
    valid: bool,
    accessible: bool,
    default_branch: str | None = None,
    archived: bool | None = None,
    visibility: str | None = None,
    result_class: str,
    error: str | None = None,
    scan_supported: bool | None = None,
) -> RepoUrlValidationResult:
    return RepoUrlValidationResult(
        valid=valid,
        provider=candidate.provider,
        provider_family=candidate.family,
        host=candidate.host,
        repo_path=candidate.repo_path,
        owner=candidate.owner,
        repo=candidate.repo,
        canonical_repo_url=candidate.canonical_repo_url,
        accessible=accessible,
        scan_supported=candidate.provider == "github" if scan_supported is None else scan_supported,
        default_branch=default_branch,
        archived=archived,
        visibility=visibility,
        confidence=candidate.confidence,
        result_class=result_class,
        error=error,
    )


def _github_repo_blocked(response: requests.Response) -> str | None:
    payload = _response_json(response) or {}
    message = str(payload.get("message") or "")
    block = payload.get("block") or {}
    if response.status_code == 403 and ("repository access blocked" in message.lower() or block):
        reason = block.get("reason")
        return f"Repository access blocked{f': {reason}' if reason else ''}"
    return None


def _parse_simple_owner_repo(host: str, segments: list[str], provider: str, family: str, *, confidence: str = "high") -> RepoUrlCandidate | None:
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1]
    repo_path = f"{owner}/{repo}"
    return RepoUrlCandidate(
        provider=provider,
        family=family,
        host=host,
        repo_path=repo_path,
        owner=owner,
        repo=repo,
        canonical_repo_url=f"https://{host}/{repo_path}",
        confidence=confidence,
    )


def _parse_github(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    return _parse_simple_owner_repo(host, segments, "github", family)


def _parse_bitbucket(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    return _parse_simple_owner_repo(host, segments, "bitbucket", family)


def _parse_codeberg(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    return _parse_simple_owner_repo(host, segments, "codeberg", family)


def _parse_sourcehut(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1]
    repo_path = f"{owner}/{repo}"
    return RepoUrlCandidate(
        provider="sourcehut",
        family=family,
        host=host,
        repo_path=repo_path,
        owner=owner,
        repo=repo,
        canonical_repo_url=f"https://{host}/{repo_path}",
        confidence="high",
    )


def _parse_gitlab(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    if "-" in segments:
        repo_segments = segments[: segments.index("-")]
    else:
        repo_segments = segments
    if len(repo_segments) < 2:
        return None
    repo_path = "/".join(repo_segments)
    return RepoUrlCandidate(
        provider="gitlab",
        family=family,
        host=host,
        repo_path=repo_path,
        owner=repo_segments[0],
        repo=repo_segments[-1],
        canonical_repo_url=f"https://{host}/{repo_path}",
        confidence="high",
    )


def _parse_gitea_like(provider: str, family: str, host: str, segments: list[str], confidence: str = "high") -> RepoUrlCandidate | None:
    return _parse_simple_owner_repo(host, segments, provider, family, confidence=confidence)


def _parse_gerrit(host: str, segments: list[str], family: str) -> RepoUrlCandidate | None:
    if not segments:
        return None
    repo_path = "/".join(segments)
    return RepoUrlCandidate(
        provider="gerrit",
        family=family,
        host=host,
        repo_path=repo_path,
        owner=None,
        repo=segments[-1],
        canonical_repo_url=f"https://{host}/{repo_path}",
        confidence="high",
    )


def _validate_github(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    response = requests.get(
        f"{GITHUB_API_ROOT}/repos/{candidate.owner}/{candidate.repo}",
        headers=_headers(github_token, accept="application/vnd.github+json"),
        timeout=request_timeout,
    )
    if response.ok:
        payload = response.json()
        owner = (payload.get("owner") or {}).get("login") or candidate.owner
        repo = payload.get("name") or candidate.repo
        repo_path = payload.get("full_name") or f"{owner}/{repo}"
        canonical = f"https://{candidate.host}/{repo_path}"
        return RepoUrlValidationResult(
            valid=True,
            provider="github",
            provider_family=candidate.family,
            host=candidate.host,
            repo_path=repo_path,
            owner=owner,
            repo=repo,
            canonical_repo_url=canonical,
            accessible=True,
            scan_supported=True,
            default_branch=payload.get("default_branch"),
            archived=payload.get("archived"),
            visibility=payload.get("visibility"),
            confidence=candidate.confidence,
            result_class="supported_repo",
            error=None,
        )
    blocked_error = _github_repo_blocked(response)
    if blocked_error:
        return _result_from_candidate(
            candidate,
            valid=True,
            accessible=False,
            result_class="valid_repo_blocked",
            error=blocked_error,
            scan_supported=True,
        )
    if response.status_code == 404:
        return _result_from_candidate(
            candidate,
            valid=False,
            accessible=False,
            result_class="repo_not_found",
            error="GitHub repository not found.",
            scan_supported=True,
        )
    return _result_from_candidate(
        candidate,
        valid=False,
        accessible=False,
        result_class="provider_api_error",
        error=f"GitHub validation failed with status {response.status_code}.",
        scan_supported=True,
    )


def _validate_gitlab(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    encoded = quote(candidate.repo_path, safe="")
    response = requests.get(
        f"https://{candidate.host}/api/v4/projects/{encoded}",
        headers=_headers(github_token),
        timeout=request_timeout,
    )
    if response.ok:
        payload = response.json()
        return RepoUrlValidationResult(
            valid=True,
            provider="gitlab",
            provider_family=candidate.family,
            host=candidate.host,
            repo_path=payload.get("path_with_namespace") or candidate.repo_path,
            owner=candidate.owner,
            repo=payload.get("path") or candidate.repo,
            canonical_repo_url=payload.get("web_url") or candidate.canonical_repo_url,
            accessible=True,
            scan_supported=False,
            default_branch=payload.get("default_branch"),
            archived=payload.get("archived"),
            visibility=payload.get("visibility"),
            confidence=candidate.confidence,
            result_class="valid_repo_unsupported_provider",
            error=None,
        )
    if response.status_code == 404:
        return _result_from_candidate(candidate, valid=False, accessible=False, result_class="repo_not_found", error="GitLab repository not found.", scan_supported=False)
    return _result_from_candidate(candidate, valid=False, accessible=False, result_class="provider_api_error", error=f"GitLab validation failed with status {response.status_code}.", scan_supported=False)


def _validate_bitbucket(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    response = requests.get(
        f"https://api.bitbucket.org/2.0/repositories/{candidate.owner}/{candidate.repo}",
        headers=_headers(github_token),
        timeout=request_timeout,
    )
    if response.ok:
        payload = response.json()
        owner = ((payload.get("owner") or {}).get("username") or (payload.get("owner") or {}).get("nickname") or candidate.owner)
        repo = payload.get("slug") or candidate.repo
        return RepoUrlValidationResult(
            valid=True,
            provider="bitbucket",
            provider_family=candidate.family,
            host=candidate.host,
            repo_path=payload.get("full_name") or candidate.repo_path,
            owner=owner,
            repo=repo,
            canonical_repo_url=((payload.get("links") or {}).get("html") or {}).get("href") or candidate.canonical_repo_url,
            accessible=True,
            scan_supported=False,
            default_branch=None,
            archived=None,
            visibility="private" if payload.get("is_private") else "public",
            confidence=candidate.confidence,
            result_class="valid_repo_unsupported_provider",
            error=None,
        )
    if response.status_code == 404:
        return _result_from_candidate(candidate, valid=False, accessible=False, result_class="repo_not_found", error="Bitbucket repository not found.", scan_supported=False)
    return _result_from_candidate(candidate, valid=False, accessible=False, result_class="provider_api_error", error=f"Bitbucket validation failed with status {response.status_code}.", scan_supported=False)


def _validate_gitea_like(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    response = requests.get(
        f"https://{candidate.host}/api/v1/repos/{candidate.owner}/{candidate.repo}",
        headers=_headers(github_token),
        timeout=request_timeout,
    )
    if response.ok:
        payload = response.json()
        return RepoUrlValidationResult(
            valid=True,
            provider=candidate.provider,
            provider_family=candidate.family,
            host=candidate.host,
            repo_path=((payload.get("owner") or {}).get("login") and payload.get("name") and f"{(payload.get('owner') or {}).get('login')}/{payload.get('name')}") or candidate.repo_path,
            owner=((payload.get("owner") or {}).get("login") or candidate.owner),
            repo=payload.get("name") or candidate.repo,
            canonical_repo_url=payload.get("html_url") or candidate.canonical_repo_url,
            accessible=True,
            scan_supported=False,
            default_branch=payload.get("default_branch"),
            archived=payload.get("archived"),
            visibility="private" if payload.get("private") else "public",
            confidence=candidate.confidence,
            result_class="valid_repo_unsupported_provider",
            error=None,
        )
    if response.status_code == 404:
        return _result_from_candidate(candidate, valid=False, accessible=False, result_class="repo_not_found", error=f"{candidate.provider.title()} repository not found.", scan_supported=False)
    return _result_from_candidate(candidate, valid=False, accessible=False, result_class="provider_api_error", error=f"{candidate.provider.title()} validation failed with status {response.status_code}.", scan_supported=False)


def _strip_gerrit_prefix(text: str) -> str:
    if text.startswith(")]}'"):
        return text.split("\n", 1)[1] if "\n" in text else ""
    return text


def _validate_gerrit(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    response = requests.get(
        f"https://{candidate.host}/projects/{quote(candidate.repo_path, safe='')}",
        headers=_headers(github_token),
        timeout=request_timeout,
    )
    if response.ok:
        body = _strip_gerrit_prefix(_response_text(response))
        payload = json.loads(body) if body else {}
        return RepoUrlValidationResult(
            valid=True,
            provider="gerrit",
            provider_family=candidate.family,
            host=candidate.host,
            repo_path=payload.get("id") or candidate.repo_path,
            owner=None,
            repo=candidate.repo,
            canonical_repo_url=candidate.canonical_repo_url,
            accessible=True,
            scan_supported=False,
            default_branch=payload.get("default_branch"),
            archived=payload.get("state") == "READ_ONLY",
            visibility=None,
            confidence=candidate.confidence,
            result_class="valid_repo_unsupported_provider",
            error=None,
        )
    if response.status_code == 404:
        return _result_from_candidate(candidate, valid=False, accessible=False, result_class="repo_not_found", error="Gerrit project not found.", scan_supported=False)
    return _result_from_candidate(candidate, valid=False, accessible=False, result_class="provider_api_error", error=f"Gerrit validation failed with status {response.status_code}.", scan_supported=False)


def _validate_sourcehut(candidate: RepoUrlCandidate, github_token: str | None, request_timeout: float) -> RepoUrlValidationResult:
    response = requests.get(
        candidate.canonical_repo_url,
        headers=_headers(github_token, accept="text/html,application/xhtml+xml"),
        timeout=request_timeout,
        allow_redirects=True,
    )
    body = _response_text(response).lower()
    if response.ok and "repository not found" not in body and candidate.repo_path.lower() in body and ("git clone" in body or "summary" in body):
        return _result_from_candidate(candidate, valid=True, accessible=True, result_class="valid_repo_unsupported_provider", scan_supported=False)
    if response.status_code == 404 or "repository not found" in body:
        return _result_from_candidate(candidate, valid=False, accessible=False, result_class="repo_not_found", error="SourceHut repository not found.", scan_supported=False)
    return _result_from_candidate(candidate, valid=False, accessible=False, result_class="provider_fingerprint_low_confidence", error="Could not confirm a SourceHut repository page with high confidence.", scan_supported=False)


def _fingerprint_json_version(host: str, path: str, marker: str, request_timeout: float) -> bool:
    try:
        response = requests.get(
            f"https://{host}{path}",
            headers=_headers(None),
            timeout=request_timeout,
        )
    except requests.RequestException:
        return False
    if not response.ok:
        return False
    payload = _response_json(response)
    if not isinstance(payload, dict):
        return False
    joined = json.dumps(payload).lower()
    return marker.lower() in joined or "version" in payload


def _fingerprint_gitlab(host: str, request_timeout: float) -> bool:
    return _fingerprint_json_version(host, "/api/v4/version", "revision", request_timeout)


def _fingerprint_gitea(host: str, request_timeout: float) -> bool:
    return _fingerprint_json_version(host, "/api/v1/version", "gitea", request_timeout)


def _fingerprint_forgejo(host: str, request_timeout: float) -> bool:
    return _fingerprint_json_version(host, "/api/v1/version", "forgejo", request_timeout)


def _fingerprint_gerrit(host: str, request_timeout: float) -> bool:
    try:
        response = requests.get(
            f"https://{host}/config/server/version",
            headers=_headers(None),
            timeout=request_timeout,
        )
    except requests.RequestException:
        return False
    if not response.ok:
        return False
    text = _response_text(response)
    return text.startswith(")]}'") or "gerrit" in text.lower()


def _match_exact_host(parsed: ParsedRepoUrlInput) -> ProviderHandler | None:
    for handler in PROVIDER_HANDLERS:
        if parsed.host in handler.exact_hosts:
            return handler
    return None


def _match_fingerprint(parsed: ParsedRepoUrlInput, request_timeout: float) -> ProviderHandler | None:
    for handler in PROVIDER_HANDLERS:
        if handler.fingerprint and handler.fingerprint(parsed.host, request_timeout):
            return handler
    return None


PROVIDER_HANDLERS: list[ProviderHandler] = [
    ProviderHandler("github", "github", True, ("github.com",), _parse_github, _validate_github),
    ProviderHandler("gitlab", "gitlab", False, ("gitlab.com",), _parse_gitlab, _validate_gitlab, fingerprint=_fingerprint_gitlab),
    ProviderHandler("bitbucket", "bitbucket", False, ("bitbucket.org",), _parse_bitbucket, _validate_bitbucket),
    ProviderHandler("codeberg", "forgejo", False, ("codeberg.org",), _parse_codeberg, _validate_gitea_like),
    ProviderHandler("sourcehut", "sourcehut", False, ("git.sr.ht",), _parse_sourcehut, _validate_sourcehut),
    ProviderHandler("forgejo", "forgejo", False, (), lambda h, s, f: _parse_gitea_like("forgejo", f, h, s), _validate_gitea_like, fingerprint=_fingerprint_forgejo),
    ProviderHandler("gitea", "gitea", False, (), lambda h, s, f: _parse_gitea_like("gitea", f, h, s), _validate_gitea_like, fingerprint=_fingerprint_gitea),
    ProviderHandler("gerrit", "gerrit", False, (), _parse_gerrit, _validate_gerrit, fingerprint=_fingerprint_gerrit),
]


def validate_repo_url(raw_url: str, *, github_token: str | None = None, request_timeout: float = 20.0) -> RepoUrlValidationResult:
    parsed = parse_raw_repo_url(raw_url)
    if parsed is None:
        return RepoUrlValidationResult(
            valid=False,
            provider=None,
            provider_family=None,
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
            confidence=None,
            result_class="invalid_url",
            error="Unsupported or invalid repository URL.",
        )

    handler = _match_exact_host(parsed)
    if handler is None:
        handler = _match_fingerprint(parsed, request_timeout)
    if handler is None:
        return RepoUrlValidationResult(
            valid=False,
            provider="unknown",
            provider_family="unknown",
            host=parsed.host,
            repo_path=None,
            owner=None,
            repo=None,
            canonical_repo_url=None,
            accessible=False,
            scan_supported=False,
            default_branch=None,
            archived=None,
            visibility=None,
            confidence="low",
            result_class="unknown_provider",
            error="Repository host is not currently recognized.",
        )

    candidate = handler.parser(parsed.host, parsed.segments, handler.family)
    if candidate is None:
        return RepoUrlValidationResult(
            valid=False,
            provider=handler.provider,
            provider_family=handler.family,
            host=parsed.host,
            repo_path=None,
            owner=None,
            repo=None,
            canonical_repo_url=None,
            accessible=False,
            scan_supported=handler.scan_supported,
            default_branch=None,
            archived=None,
            visibility=None,
            confidence="low",
            result_class="provider_fingerprint_low_confidence",
            error=f"URL did not match an expected {handler.provider} repository path.",
        )

    try:
        return handler.validator(candidate, github_token, request_timeout)
    except requests.RequestException as exc:
        return _result_from_candidate(
            candidate,
            valid=False,
            accessible=False,
            result_class="validation_error",
            error=f"Validation request failed: {exc}",
            scan_supported=handler.scan_supported,
        )
    except Exception as exc:
        return _result_from_candidate(
            candidate,
            valid=False,
            accessible=False,
            result_class="validation_error",
            error=f"Validation failed: {exc}",
            scan_supported=handler.scan_supported,
        )
