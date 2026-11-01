import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import requests
from dotenv import load_dotenv

from storage.logging_config import configure_logging
from storage.secrets import get_secret


LOGGER = logging.getLogger("repo_practice_signals")
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".cache" / "repo_practice_signals"
GITHUB_API_ROOT = "https://api.github.com"
API_VERSION = "2026-03-10"
STANDARD_COMMUNITY_DIRS = {"", ".github", "docs"}
GOVERNANCE_STRONG_BASENAMES = {
    "governance",
    "governance.md",
    "governance.rst",
    "governance.txt",
    "maintainers",
    "maintainers.md",
    "maintainers.rst",
    "maintainers.txt",
    "owners",
    "owners.md",
    "owners.rst",
    "owners.txt",
    "codeowners",
}
CONTRIBUTING_BASENAMES = {
    "contributing",
    "contributing.md",
    "contributing.rst",
    "contributing.txt",
}
CONTAINERIZATION_STRONG_BASENAMES = {
    "dockerfile",
    "containerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
CONTAINERIZATION_MEDIUM_BASENAMES = {
    ".dockerignore",
    "chart.yaml",
    "helmfile.yaml",
    "kustomization.yaml",
    "skaffold.yaml",
    "docker-bake.hcl",
}


class GitHubRepoBlockedError(RuntimeError):
    def __init__(self, *, url: str, status_code: int, message: str, block: dict[str, Any] | None):
        super().__init__(message)
        self.url = url
        self.status_code = status_code
        self.message = message
        self.block = block or {}


def blocked_repo_payload(response: requests.Response) -> dict[str, Any] | None:
    if response.status_code != 403:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None

    message = str(payload.get("message") or "")
    block = payload.get("block") or None
    if "repository access blocked" not in message.lower() and not block:
        return None

    return {
        "url": response.url,
        "status_code": response.status_code,
        "message": message or "Repository access blocked",
        "block": block,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimentally collect GitHub policy/governance/containerization signals for repos.",
    )
    parser.add_argument("--owner", required=True, help="GitHub owner/org to analyze")
    parser.add_argument("--repo", help="Optional repo name to limit the analysis")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for outputs and caches (default: .cache/repo_practice_signals)",
    )
    parser.add_argument(
        "--max-repos",
        type=int,
        help="Optional limit after repo discovery",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore cached GitHub responses and refetch them",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay between uncached GitHub requests",
    )
    return parser.parse_args()


def scope_slug(owner: str, repo: str | None) -> str:
    return f"{owner}__{repo}" if repo else owner


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_cache(path: Path, data: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "maturity-tool-repo-practice-signals",
        "X-GitHub-Api-Version": API_VERSION,
    }


def response_snippet(response: requests.Response, limit: int = 500) -> str:
    text = (response.text or "").strip()
    return text[:limit]


def cached_get_json(
    session: requests.Session,
    url: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
    allow_statuses: set[int] | None = None,
) -> Any:
    cache_key = url
    if not refresh_cache and cache_key in cache:
        cached = cache[cache_key]
        if cached.get("blocked"):
            blocked = cached["blocked"]
            raise GitHubRepoBlockedError(
                url=blocked.get("url") or url,
                status_code=int(blocked.get("status_code") or 403),
                message=blocked.get("message") or "Repository access blocked",
                block=blocked.get("block"),
            )
        return cached.get("data")

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    response = session.get(url)
    blocked = blocked_repo_payload(response)
    if blocked:
        cache[cache_key] = {
            "fetched_at": pd.Timestamp.utcnow().isoformat(),
            "status_code": response.status_code,
            "data": None,
            "blocked": blocked,
        }
        save_json_cache(cache_path, cache)
        raise GitHubRepoBlockedError(
            url=blocked["url"],
            status_code=blocked["status_code"],
            message=blocked["message"],
            block=blocked.get("block"),
        )
    if allow_statuses and response.status_code in allow_statuses:
        data = None
    elif not response.ok:
        raise RuntimeError(
            f"GET {response.url} failed: {response.status_code} {response_snippet(response)}"
        )
    else:
        data = response.json()

    cache[cache_key] = {
        "fetched_at": pd.Timestamp.utcnow().isoformat(),
        "status_code": response.status_code,
        "data": data,
    }
    save_json_cache(cache_path, cache)
    return data


def list_repos_for_owner(
    session: requests.Session,
    owner: str,
    *,
    max_repos: int | None,
) -> list[str]:
    repos = []
    page = 1
    while True:
        response = session.get(
            f"{GITHUB_API_ROOT}/users/{owner}/repos",
            params={
                "type": "owner",
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            },
        )
        if not response.ok:
            raise RuntimeError(
                f"GET {response.url} failed: {response.status_code} {response_snippet(response)}"
            )
        data = response.json()
        if not data:
            break
        repos.extend(item["name"] for item in data)
        if max_repos is not None and len(repos) >= max_repos:
            return repos[:max_repos]
        if len(data) < 100:
            break
        page += 1
    return repos


def fetch_repo_details(
    session: requests.Session,
    owner: str,
    repo: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> dict[str, Any]:
    url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}"
    data = cached_get_json(
        session,
        url,
        cache=cache,
        cache_path=cache_path,
        refresh_cache=refresh_cache,
        delay_seconds=delay_seconds,
    )
    return data or {}


def fetch_community_profile(
    session: requests.Session,
    owner: str,
    repo: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> dict[str, Any] | None:
    url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}/community/profile"
    return cached_get_json(
        session,
        url,
        cache=cache,
        cache_path=cache_path,
        refresh_cache=refresh_cache,
        delay_seconds=delay_seconds,
        allow_statuses={404},
    )


def fetch_repo_tree(
    session: requests.Session,
    owner: str,
    repo: str,
    default_branch: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> dict[str, Any] | None:
    url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1"
    return cached_get_json(
        session,
        url,
        cache=cache,
        cache_path=cache_path,
        refresh_cache=refresh_cache,
        delay_seconds=delay_seconds,
        allow_statuses={404, 409},
    )


def normalize_path(path: str) -> str:
    return path.strip().strip("/").lower()


def split_path(path: str) -> tuple[str, str]:
    normalized = normalize_path(path)
    if "/" not in normalized:
        return "", normalized
    dirname, basename = normalized.rsplit("/", 1)
    return dirname, basename


def tree_blob_paths(tree_payload: dict[str, Any] | None) -> list[str]:
    if not tree_payload:
        return []
    paths = []
    for entry in tree_payload.get("tree") or []:
        if entry.get("type") == "blob" and entry.get("path"):
            paths.append(normalize_path(entry["path"]))
    return paths


def standard_location_matches(paths: list[str], basenames: set[str]) -> list[str]:
    matches = []
    for path in paths:
        dirname, basename = split_path(path)
        if dirname in STANDARD_COMMUNITY_DIRS and basename in basenames:
            matches.append(path)
    return sorted(set(matches))


def any_basename_matches(paths: list[str], basenames: set[str]) -> list[str]:
    matches = []
    for path in paths:
        _, basename = split_path(path)
        if basename in basenames:
            matches.append(path)
    return sorted(set(matches))


def prefix_matches(paths: list[str], prefixes: list[str]) -> list[str]:
    matches = []
    normalized_prefixes = [normalize_path(prefix).rstrip("/") + "/" for prefix in prefixes]
    for path in paths:
        if any(path.startswith(prefix) for prefix in normalized_prefixes):
            matches.append(path)
    return sorted(set(matches))


def workflow_medium_matches(paths: list[str]) -> list[str]:
    matches = []
    for path in paths:
        dirname, basename = split_path(path)
        if dirname == ".github/workflows" and any(
            token in basename for token in ["docker", "container", "helm", "kustom", "skaffold"]
        ):
            matches.append(path)
    return sorted(set(matches))


def devcontainer_matches(paths: list[str]) -> list[str]:
    matches = []
    for path in paths:
        dirname, basename = split_path(path)
        if basename == "devcontainer.json" and (
            dirname == ".devcontainer" or dirname.endswith("/.devcontainer")
        ):
            matches.append(path)
    return sorted(set(matches))


def detect_security_policy(paths: list[str], repo_details: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    policy_signals = standard_location_matches(paths, {"security.md"})
    analysis = repo_details.get("security_and_analysis") or {}
    analysis_signals = []
    for key, value in analysis.items():
        status = (value or {}).get("status")
        if status == "enabled":
            analysis_signals.append(f"security_and_analysis.{key}=enabled")
    return bool(policy_signals), policy_signals, analysis_signals


def detect_code_of_conduct(
    paths: list[str],
    repo_details: dict[str, Any],
    community_profile: dict[str, Any] | None,
) -> tuple[bool, list[str]]:
    signals = []
    if repo_details.get("code_of_conduct"):
        signals.append("repo.code_of_conduct")

    files = (community_profile or {}).get("files") or {}
    if files.get("code_of_conduct") or files.get("code_of_conduct_file"):
        signals.append("community_profile.code_of_conduct")

    file_matches = standard_location_matches(
        paths,
        {"code_of_conduct", "code_of_conduct.md", "code_of_conduct.rst", "code_of_conduct.txt"},
    )
    signals.extend(file_matches)
    return bool(signals), sorted(set(signals))


def detect_governance(paths: list[str], community_profile: dict[str, Any] | None) -> tuple[bool, str, list[str], list[str]]:
    strong_signals = standard_location_matches(paths, GOVERNANCE_STRONG_BASENAMES)
    medium_signals = []
    medium_categories = set()

    contributing_files = standard_location_matches(paths, CONTRIBUTING_BASENAMES)
    if contributing_files:
        medium_categories.add("contributing")
        medium_signals.extend(contributing_files)

    issue_template_files = prefix_matches(paths, [".github/issue_template"])
    issue_template_files.extend(standard_location_matches(paths, {"issue_template.md"}))
    if issue_template_files:
        medium_categories.add("issue_templates")
        medium_signals.extend(issue_template_files)

    pr_template_files = prefix_matches(paths, [".github/pull_request_template"])
    pr_template_files.extend(standard_location_matches(paths, {"pull_request_template.md"}))
    if pr_template_files:
        medium_categories.add("pull_request_templates")
        medium_signals.extend(pr_template_files)

    files = (community_profile or {}).get("files") or {}
    if files.get("contributing"):
        medium_categories.add("contributing")
        medium_signals.append("community_profile.contributing")
    if files.get("issue_template"):
        medium_categories.add("issue_templates")
        medium_signals.append("community_profile.issue_template")
    if files.get("pull_request_template"):
        medium_categories.add("pull_request_templates")
        medium_signals.append("community_profile.pull_request_template")

    if strong_signals:
        return True, "strong", sorted(set(strong_signals)), sorted(set(medium_signals))
    if len(medium_categories) >= 2:
        return True, "medium", [], sorted(set(medium_signals))
    return False, "none", [], sorted(set(medium_signals))


def detect_containerization(paths: list[str]) -> tuple[bool, str, list[str], list[str]]:
    strong_signals = any_basename_matches(paths, CONTAINERIZATION_STRONG_BASENAMES)
    strong_signals.extend(devcontainer_matches(paths))

    medium_signals = any_basename_matches(paths, CONTAINERIZATION_MEDIUM_BASENAMES)
    medium_signals.extend(workflow_medium_matches(paths))

    if strong_signals:
        return True, "strong", sorted(set(strong_signals)), sorted(set(medium_signals))
    if medium_signals:
        return True, "medium", [], sorted(set(medium_signals))
    return False, "none", [], []


def blocked_repo_row(owner: str, repo: str, exc: GitHubRepoBlockedError) -> dict[str, Any]:
    block = exc.block or {}
    return {
        "owner": owner,
        "repo": repo,
        "scan_status": "blocked",
        "blocked_reason": block.get("reason"),
        "blocked_created_at": block.get("created_at"),
        "blocked_html_url": block.get("html_url"),
        "error_message": exc.message,
        "default_branch": None,
        "is_fork": None,
        "is_archived": None,
        "visibility": None,
        "has_security_policy": None,
        "has_governance": None,
        "has_code_of_conduct": None,
        "has_containerization": None,
        "governance_confidence": None,
        "containerization_confidence": None,
        "community_health_percentage": None,
        "community_profile_available": None,
        "tree_scan_available": None,
        "tree_truncated": None,
        "code_of_conduct_key": None,
        "has_contributing_file": None,
        "has_issue_template": None,
        "has_pr_template": None,
        "security_policy_signals": [],
        "security_analysis_signals": [],
        "code_of_conduct_signals": [],
        "governance_strong_signals": [],
        "governance_medium_signals": [],
        "containerization_strong_signals": [],
        "containerization_medium_signals": [],
        "security_and_analysis": None,
        "topics": [],
        "html_url": None,
    }


def error_repo_row(owner: str, repo: str, message: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "repo": repo,
        "scan_status": "error",
        "blocked_reason": None,
        "blocked_created_at": None,
        "blocked_html_url": None,
        "error_message": message,
        "default_branch": None,
        "is_fork": None,
        "is_archived": None,
        "visibility": None,
        "has_security_policy": None,
        "has_governance": None,
        "has_code_of_conduct": None,
        "has_containerization": None,
        "governance_confidence": None,
        "containerization_confidence": None,
        "community_health_percentage": None,
        "community_profile_available": None,
        "tree_scan_available": None,
        "tree_truncated": None,
        "code_of_conduct_key": None,
        "has_contributing_file": None,
        "has_issue_template": None,
        "has_pr_template": None,
        "security_policy_signals": [],
        "security_analysis_signals": [],
        "code_of_conduct_signals": [],
        "governance_strong_signals": [],
        "governance_medium_signals": [],
        "containerization_strong_signals": [],
        "containerization_medium_signals": [],
        "security_and_analysis": None,
        "topics": [],
        "html_url": None,
    }


def analyze_repo(
    session: requests.Session,
    owner: str,
    repo: str,
    *,
    repo_cache: dict[str, Any],
    repo_cache_path: Path,
    community_cache: dict[str, Any],
    community_cache_path: Path,
    tree_cache: dict[str, Any],
    tree_cache_path: Path,
    refresh_cache: bool,
    request_delay_seconds: float,
) -> dict[str, Any]:
    LOGGER.info("Collecting practice signals for %s/%s", owner, repo)
    try:
        repo_details = fetch_repo_details(
            session,
            owner,
            repo,
            cache=repo_cache,
            cache_path=repo_cache_path,
            refresh_cache=refresh_cache,
            delay_seconds=request_delay_seconds,
        )
        default_branch = repo_details.get("default_branch")
        community_profile = fetch_community_profile(
            session,
            owner,
            repo,
            cache=community_cache,
            cache_path=community_cache_path,
            refresh_cache=refresh_cache,
            delay_seconds=request_delay_seconds,
        )
        tree_payload = None
        if default_branch:
            tree_payload = fetch_repo_tree(
                session,
                owner,
                repo,
                default_branch,
                cache=tree_cache,
                cache_path=tree_cache_path,
                refresh_cache=refresh_cache,
                delay_seconds=request_delay_seconds,
            )
        paths = tree_blob_paths(tree_payload)

        has_security_policy, security_policy_signals, security_analysis_signals = detect_security_policy(paths, repo_details)
        has_code_of_conduct, code_of_conduct_signals = detect_code_of_conduct(paths, repo_details, community_profile)
        has_governance, governance_confidence, governance_strong_signals, governance_medium_signals = detect_governance(
            paths,
            community_profile,
        )
        has_containerization, containerization_confidence, containerization_strong_signals, containerization_medium_signals = detect_containerization(paths)

        files = (community_profile or {}).get("files") or {}
        return {
            "owner": owner,
            "repo": repo,
            "scan_status": "ok",
            "blocked_reason": None,
            "blocked_created_at": None,
            "blocked_html_url": None,
            "error_message": None,
            "default_branch": default_branch,
            "is_fork": bool(repo_details.get("fork")),
            "is_archived": bool(repo_details.get("archived")),
            "visibility": repo_details.get("visibility"),
            "has_security_policy": has_security_policy,
            "has_governance": has_governance,
            "has_code_of_conduct": has_code_of_conduct,
            "has_containerization": has_containerization,
            "governance_confidence": governance_confidence,
            "containerization_confidence": containerization_confidence,
            "community_health_percentage": (community_profile or {}).get("health_percentage"),
            "community_profile_available": community_profile is not None,
            "tree_scan_available": tree_payload is not None,
            "tree_truncated": (tree_payload or {}).get("truncated"),
            "code_of_conduct_key": (repo_details.get("code_of_conduct") or {}).get("key"),
            "has_contributing_file": bool(files.get("contributing")),
            "has_issue_template": bool(files.get("issue_template")),
            "has_pr_template": bool(files.get("pull_request_template")),
            "security_policy_signals": security_policy_signals,
            "security_analysis_signals": security_analysis_signals,
            "code_of_conduct_signals": code_of_conduct_signals,
            "governance_strong_signals": governance_strong_signals,
            "governance_medium_signals": governance_medium_signals,
            "containerization_strong_signals": containerization_strong_signals,
            "containerization_medium_signals": containerization_medium_signals,
            "security_and_analysis": repo_details.get("security_and_analysis"),
            "topics": repo_details.get("topics") or [],
            "html_url": repo_details.get("html_url"),
        }
    except GitHubRepoBlockedError as exc:
        LOGGER.warning(
            "Repository blocked for %s/%s reason=%s tos_url=%s",
            owner,
            repo,
            (exc.block or {}).get("reason"),
            (exc.block or {}).get("html_url"),
        )
        return blocked_repo_row(owner, repo, exc)
    except Exception as exc:
        LOGGER.exception("Failed to collect practice signals for %s/%s", owner, repo)
        return error_repo_row(owner, repo, str(exc))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        with path.open("w", encoding="utf-8") as handle:
            handle.write("")
        return
    pd.DataFrame(rows).to_csv(path, index=False)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def build_summary(rows: list[dict[str, Any]], owner: str, repo: str | None, max_repos: int | None) -> dict[str, Any]:
    total = len(rows)
    ok_rows = [row for row in rows if row.get("scan_status") == "ok"]
    summary = {
        "owner": owner,
        "repo": repo,
        "repos_scanned": total,
        "repos_completed": len(ok_rows),
        "repos_blocked": sum(1 for row in rows if row.get("scan_status") == "blocked"),
        "repos_failed": sum(1 for row in rows if row.get("scan_status") == "error"),
        "max_repos": max_repos,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
    }
    for key in [
        "has_security_policy",
        "has_governance",
        "has_code_of_conduct",
        "has_containerization",
    ]:
        summary[key] = int(sum(1 for row in ok_rows if row.get(key)))

    summary["governance_strong"] = int(sum(1 for row in ok_rows if row.get("governance_confidence") == "strong"))
    summary["governance_medium"] = int(sum(1 for row in ok_rows if row.get("governance_confidence") == "medium"))
    summary["containerization_strong"] = int(sum(1 for row in ok_rows if row.get("containerization_confidence") == "strong"))
    summary["containerization_medium"] = int(sum(1 for row in ok_rows if row.get("containerization_confidence") == "medium"))
    summary["community_profile_available"] = int(sum(1 for row in ok_rows if row.get("community_profile_available")))
    summary["tree_scan_available"] = int(sum(1 for row in ok_rows if row.get("tree_scan_available")))
    summary["tree_truncated"] = int(sum(1 for row in ok_rows if row.get("tree_truncated")))
    return summary


def main() -> None:
    configure_logging()
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()

    token = get_secret("GITHUB_TOKEN", required=True)
    output_root = Path(args.output_root)
    output_dir = output_root / scope_slug(args.owner, args.repo)
    cache_dir = output_root / "caches"
    ensure_dir(output_dir)
    ensure_dir(cache_dir)

    repo_cache_path = cache_dir / "repo_details.json"
    community_cache_path = cache_dir / "community_profiles.json"
    tree_cache_path = cache_dir / "repo_trees.json"
    repo_cache = load_json_cache(repo_cache_path)
    community_cache = load_json_cache(community_cache_path)
    tree_cache = load_json_cache(tree_cache_path)

    session = requests.Session()
    session.headers.update(github_headers(token))

    if args.repo:
        repos = [args.repo]
    else:
        repos = list_repos_for_owner(session, args.owner, max_repos=args.max_repos)
    if args.max_repos is not None:
        repos = repos[: args.max_repos]

    rows = []
    for repo_name in repos:
        rows.append(
            analyze_repo(
                session,
                args.owner,
                repo_name,
                repo_cache=repo_cache,
                repo_cache_path=repo_cache_path,
                community_cache=community_cache,
                community_cache_path=community_cache_path,
                tree_cache=tree_cache,
                tree_cache_path=tree_cache_path,
                refresh_cache=args.refresh_cache,
                request_delay_seconds=args.request_delay_seconds,
            )
        )

    summary = build_summary(rows, args.owner, args.repo, args.max_repos)
    write_csv(output_dir / "repo_practice_signals.csv", rows)
    write_json(output_dir / "repo_practice_signals.json", rows)
    write_json(output_dir / "summary.json", summary)

    LOGGER.info(
        "Wrote repo practice signals to %s (repos=%s, security=%s, governance=%s, conduct=%s, containerization=%s)",
        output_dir,
        summary["repos_scanned"],
        summary["has_security_policy"],
        summary["has_governance"],
        summary["has_code_of_conduct"],
        summary["has_containerization"],
    )


if __name__ == "__main__":
    main()
