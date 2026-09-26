"""Experimentally collect known vulnerabilities for exact locked dependencies.

This collector intentionally stays outside the product data pipeline. It only
reports vulnerabilities for package versions found in supported lockfiles; a
missing or unsupported lockfile is reported as incomplete coverage, not clean
security posture.
"""

import argparse
import base64
import json
import logging
from pathlib import Path
import re
import sys
import time
import tomllib
from typing import Any
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import requests
from dotenv import load_dotenv

from storage.logging_config import configure_logging
from storage.secrets import get_secret


LOGGER = logging.getLogger("dependency_vulnerabilities")
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".cache" / "dependency_vulnerabilities"
GITHUB_API_ROOT = "https://api.github.com"
DEPS_API_ROOT = "https://api.deps.dev/v3alpha"
GITHUB_API_VERSION = "2026-03-10"
VERSION_BATCH_SIZE = 5000
SUPPORTED_LOCKFILES = {
    "package-lock.json": "npm",
    "go.sum": "go",
    "cargo.lock": "cargo",
    "poetry.lock": "pypi",
}
REQUIREMENTS_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)")


class GitHubRepoBlockedError(RuntimeError):
    def __init__(self, message: str, block: dict[str, Any] | None = None):
        super().__init__(message)
        self.block = block or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimentally collect vulnerabilities from supported exact-version lockfiles.",
    )
    parser.add_argument("--owner", required=True, help="GitHub owner/org to analyze")
    parser.add_argument("--repo", help="Optional repo name to limit the analysis")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--max-repos", type=int, help="Optional limit after repo discovery")
    parser.add_argument("--refresh-cache", action="store_true", help="Ignore cached API responses")
    parser.add_argument("--request-delay-seconds", type=float, default=0.0)
    return parser.parse_args()


def scope_slug(owner: str, repo: str | None) -> str:
    return f"{owner}__{repo}" if repo else owner


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def github_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "maturity-tool-dependency-vulnerabilities",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def cached_github_json(
    session: requests.Session,
    url: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
    allow_statuses: set[int] | None = None,
) -> Any:
    if not refresh_cache and url in cache:
        cached = cache[url]
        if cached.get("blocked"):
            raise GitHubRepoBlockedError(cached["blocked"].get("message", "Repository access blocked"), cached["blocked"])
        return cached.get("data")
    if delay_seconds:
        time.sleep(delay_seconds)
    response = session.get(url, timeout=30)
    payload = response.json() if response.content else None
    if response.status_code == 403 and isinstance(payload, dict) and (
        payload.get("block") or "repository access blocked" in str(payload.get("message", "")).lower()
    ):
        block = payload.get("block") or {}
        blocked = {"message": payload.get("message", "Repository access blocked"), **block}
        cache[url] = {"blocked": blocked, "data": None}
        save_json(cache_path, cache)
        raise GitHubRepoBlockedError(blocked["message"], blocked)
    if allow_statuses and response.status_code in allow_statuses:
        payload = None
    elif not response.ok:
        raise RuntimeError(f"GET {response.url} failed: {response.status_code} {(response.text or '')[:500]}")
    cache[url] = {"data": payload, "status_code": response.status_code}
    save_json(cache_path, cache)
    return payload


def list_repos(session: requests.Session, owner: str, max_repos: int | None) -> list[str]:
    repos = []
    for page in range(1, 100):
        response = session.get(
            f"{GITHUB_API_ROOT}/users/{owner}/repos",
            params={"type": "owner", "per_page": 100, "page": page, "sort": "updated", "direction": "desc"},
            timeout=30,
        )
        if not response.ok:
            raise RuntimeError(f"Could not list repositories: {response.status_code} {response.text[:500]}")
        data = response.json()
        repos.extend(item["name"] for item in data)
        if max_repos is not None and len(repos) >= max_repos:
            return repos[:max_repos]
        if len(data) < 100:
            return repos
    return repos


def tree_paths(tree: dict[str, Any] | None) -> list[str]:
    return sorted(
        entry["path"]
        for entry in (tree or {}).get("tree", [])
        if entry.get("type") == "blob" and entry.get("path")
    )


def supported_lockfile_paths(paths: list[str]) -> list[str]:
    matches = []
    for path in paths:
        basename = path.rsplit("/", 1)[-1].lower()
        if basename in SUPPORTED_LOCKFILES or basename.startswith("requirements") and basename.endswith(".txt"):
            matches.append(path)
    return matches


def detected_dependency_files(paths: list[str]) -> list[str]:
    names = {"package.json", "package-lock.json", "go.mod", "go.sum", "cargo.toml", "cargo.lock", "pyproject.toml", "poetry.lock", "pom.xml", "build.gradle", "build.gradle.kts"}
    return sorted(path for path in paths if path.rsplit("/", 1)[-1].lower() in names or path.rsplit("/", 1)[-1].lower().startswith("requirements"))


def dependency(system: str, name: str, version: str, path: str, relationship: str) -> dict[str, str]:
    return {"system": system, "name": name, "version": version, "path": path, "relationship": relationship}


def package_name_from_lock_path(lock_path: str) -> str | None:
    marker = "node_modules/"
    if marker not in lock_path:
        return None
    return lock_path.rsplit(marker, 1)[1]


def parse_package_lock(text: str, path: str) -> list[dict[str, str]]:
    data = json.loads(text)
    if data.get("lockfileVersion", 0) < 2 or not isinstance(data.get("packages"), dict):
        raise ValueError("package-lock.json requires lockfileVersion 2 or 3")
    root = data["packages"].get("", {})
    direct_names = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        direct_names.update((root.get(key) or {}).keys())
    dependencies = []
    for lock_path, entry in data["packages"].items():
        if not lock_path or not isinstance(entry, dict) or not entry.get("version"):
            continue
        name = entry.get("name") or package_name_from_lock_path(lock_path)
        if not name:
            continue
        relationship = "direct" if name in direct_names else "transitive"
        dependencies.append(dependency("NPM", name, str(entry["version"]), path, relationship))
    return dependencies


def parse_go_sum(text: str, path: str) -> list[dict[str, str]]:
    dependencies = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1].endswith("/go.mod"):
            continue
        dependencies.append(dependency("GO", parts[0], parts[1], path, "unknown"))
    return dependencies


def parse_cargo_lock(text: str, path: str) -> list[dict[str, str]]:
    data = tomllib.loads(text)
    return [
        dependency("CARGO", item["name"], str(item["version"]), path, "unknown")
        for item in data.get("package", [])
        if item.get("source") and item.get("name") and item.get("version")
    ]


def parse_poetry_lock(text: str, path: str) -> list[dict[str, str]]:
    data = tomllib.loads(text)
    return [
        dependency("PYPI", item["name"], str(item["version"]), path, "unknown")
        for item in data.get("package", [])
        if item.get("name") and item.get("version") and item.get("source", {}).get("type", "legacy") != "directory"
    ]


def parse_requirements(text: str, path: str) -> list[dict[str, str]]:
    dependencies = []
    for line in text.splitlines():
        match = REQUIREMENTS_RE.match(line)
        if match:
            dependencies.append(dependency("PYPI", match.group(1), match.group(2), path, "direct"))
    return dependencies


def parse_lockfile(path: str, text: str) -> list[dict[str, str]]:
    basename = path.rsplit("/", 1)[-1].lower()
    if basename == "package-lock.json":
        return parse_package_lock(text, path)
    if basename == "go.sum":
        return parse_go_sum(text, path)
    if basename == "cargo.lock":
        return parse_cargo_lock(text, path)
    if basename == "poetry.lock":
        return parse_poetry_lock(text, path)
    if basename.startswith("requirements") and basename.endswith(".txt"):
        return parse_requirements(text, path)
    raise ValueError(f"Unsupported lockfile: {path}")


def merge_dependencies(dependencies: list[dict[str, str]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in dependencies:
        key = (item["system"], item["name"], item["version"])
        current = merged.setdefault(
            key,
            {"system": item["system"], "name": item["name"], "version": item["version"], "paths": [], "relationship": item["relationship"]},
        )
        current["paths"].append(item["path"])
        if item["relationship"] == "direct":
            current["relationship"] = "direct"
        elif item["relationship"] == "transitive" and current["relationship"] == "unknown":
            current["relationship"] = "transitive"
    for item in merged.values():
        item["paths"] = sorted(set(item["paths"]))
    return sorted(merged.values(), key=lambda item: (item["system"], item["name"], item["version"]))


def version_cache_key(item: dict[str, Any]) -> str:
    return f"{item['system']}|{item['name']}|{item['version']}"


def fetch_versions(
    session: requests.Session,
    dependencies: list[dict[str, Any]],
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
) -> dict[str, Any]:
    requested = {version_cache_key(item): item for item in dependencies}
    missing = [item for key, item in requested.items() if refresh_cache or key not in cache]
    for start in range(0, len(missing), VERSION_BATCH_SIZE):
        batch = missing[start : start + VERSION_BATCH_SIZE]
        response = session.post(
            f"{DEPS_API_ROOT}/versionbatch",
            json={"requests": [{"versionKey": {key: item[key.lower()] for key in ("system", "name", "version")}} for item in batch]},
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f"deps.dev version batch failed: {response.status_code} {(response.text or '')[:500]}")
        by_request = {
            version_cache_key(item): item
            for item in batch
        }
        for result in response.json().get("responses", []):
            request = result.get("request", {}).get("versionKey", {})
            key = f"{request.get('system')}|{request.get('name')}|{request.get('version')}"
            if key in by_request:
                cache[key] = result.get("version")
        for item in batch:
            cache.setdefault(version_cache_key(item), None)
        save_json(cache_path, cache)
    return {key: cache.get(key) for key in requested}


def fetch_advisories(
    session: requests.Session,
    advisory_ids: set[str],
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
) -> dict[str, Any]:
    for advisory_id in sorted(advisory_ids):
        if not refresh_cache and advisory_id in cache:
            continue
        response = session.get(f"{DEPS_API_ROOT}/advisories/{quote(advisory_id, safe='')}", timeout=30)
        if response.status_code == 404:
            cache[advisory_id] = None
        elif not response.ok:
            raise RuntimeError(f"deps.dev advisory lookup failed: {response.status_code} {(response.text or '')[:500]}")
        else:
            cache[advisory_id] = response.json()
        save_json(cache_path, cache)
    return {advisory_id: cache.get(advisory_id) for advisory_id in advisory_ids}


def cvss_severity(score: Any) -> str:
    if not isinstance(score, (int, float)):
        return "unknown"
    if score >= 9:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    if score > 0:
        return "low"
    return "unknown"


def vulnerability_rows(owner: str, repo: str, dependencies: list[dict[str, Any]], versions: dict[str, Any], advisories: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in dependencies:
        version = versions.get(version_cache_key(item)) or {}
        for advisory_key in version.get("advisoryKeys", []):
            advisory_id = advisory_key.get("id")
            if not advisory_id:
                continue
            advisory = advisories.get(advisory_id) or {}
            score = advisory.get("cvss3Score")
            rows.append(
                {
                    "owner": owner,
                    "repo": repo,
                    "system": item["system"],
                    "package": item["name"],
                    "version": item["version"],
                    "purl": version.get("purl"),
                    "relationship": item["relationship"],
                    "lockfile_paths": item["paths"],
                    "advisory_id": advisory_id,
                    "aliases": advisory.get("aliases") or [],
                    "title": advisory.get("title"),
                    "cvss3_score": score,
                    "cvss3_vector": advisory.get("cvss3Vector"),
                    "severity": cvss_severity(score),
                }
            )
    return rows


def fetch_file_text(session: requests.Session, owner: str, repo: str, path: str, branch: str, **cache_args: Any) -> str:
    url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}/contents/{quote(path, safe='/')}?ref={quote(branch, safe='')}"
    payload = cached_github_json(session, url, **cache_args)
    if not payload or payload.get("encoding") != "base64":
        raise ValueError(f"Could not read lockfile content: {path}")
    return base64.b64decode(payload["content"]).decode("utf-8")


def analyze_repo(
    session: requests.Session,
    owner: str,
    repo: str,
    *,
    github_cache: dict[str, Any],
    github_cache_path: Path,
    version_cache: dict[str, Any],
    version_cache_path: Path,
    advisory_cache: dict[str, Any],
    advisory_cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        repo_url = f"{GITHUB_API_ROOT}/repos/{owner}/{repo}"
        details = cached_github_json(session, repo_url, cache=github_cache, cache_path=github_cache_path, refresh_cache=refresh_cache, delay_seconds=delay_seconds)
        branch = details.get("default_branch")
        tree = cached_github_json(session, f"{repo_url}/git/trees/{quote(branch, safe='')}?recursive=1", cache=github_cache, cache_path=github_cache_path, refresh_cache=refresh_cache, delay_seconds=delay_seconds, allow_statuses={404, 409}) if branch else None
        paths = tree_paths(tree)
        lockfiles = supported_lockfile_paths(paths)
        evidence_files = detected_dependency_files(paths)
        base_row = {"owner": owner, "repo": repo, "default_branch": branch, "html_url": details.get("html_url"), "dependency_files": evidence_files, "lockfiles": lockfiles, "tree_truncated": (tree or {}).get("truncated", False)}
        if not lockfiles:
            status = "no_supported_lockfile" if evidence_files else "no_dependency_files"
            return ({**base_row, "scan_status": status, "error_message": None, "packages_resolved": 0, "direct_packages": 0, "transitive_packages": 0, "unknown_relationship_packages": 0, "packages_with_known_advisories": 0, "vulnerabilities": 0}, [])
        dependencies = []
        parse_errors = []
        cache_args = {"cache": github_cache, "cache_path": github_cache_path, "refresh_cache": refresh_cache, "delay_seconds": delay_seconds}
        for path in lockfiles:
            try:
                dependencies.extend(parse_lockfile(path, fetch_file_text(session, owner, repo, path, branch, **cache_args)))
            except Exception as exc:
                parse_errors.append(f"{path}: {exc}")
        dependencies = merge_dependencies(dependencies)
        versions = fetch_versions(session, dependencies, cache=version_cache, cache_path=version_cache_path, refresh_cache=refresh_cache)
        advisory_ids = {key["id"] for version in versions.values() if version for key in version.get("advisoryKeys", []) if key.get("id")}
        advisories = fetch_advisories(session, advisory_ids, cache=advisory_cache, cache_path=advisory_cache_path, refresh_cache=refresh_cache)
        rows = vulnerability_rows(owner, repo, dependencies, versions, advisories)
        return ({
            **base_row,
            "scan_status": "ok" if not parse_errors else "partial",
            "error_message": "; ".join(parse_errors) or None,
            "packages_resolved": len(dependencies),
            "direct_packages": sum(item["relationship"] == "direct" for item in dependencies),
            "transitive_packages": sum(item["relationship"] == "transitive" for item in dependencies),
            "unknown_relationship_packages": sum(item["relationship"] == "unknown" for item in dependencies),
            "packages_with_known_advisories": len({(row["system"], row["package"], row["version"]) for row in rows}),
            "vulnerabilities": len(rows),
        }, rows)
    except GitHubRepoBlockedError as exc:
        return ({"owner": owner, "repo": repo, "scan_status": "blocked", "error_message": str(exc), "dependency_files": [], "lockfiles": [], "packages_resolved": 0, "direct_packages": 0, "transitive_packages": 0, "unknown_relationship_packages": 0, "packages_with_known_advisories": 0, "vulnerabilities": 0}, [])
    except Exception as exc:
        LOGGER.exception("Failed to collect dependencies for %s/%s", owner, repo)
        return ({"owner": owner, "repo": repo, "scan_status": "error", "error_message": str(exc), "dependency_files": [], "lockfiles": [], "packages_resolved": 0, "direct_packages": 0, "transitive_packages": 0, "unknown_relationship_packages": 0, "packages_with_known_advisories": 0, "vulnerabilities": 0}, [])


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> None:
    configure_logging()
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()
    output_dir = Path(args.output_root) / scope_slug(args.owner, args.repo)
    cache_dir = Path(args.output_root) / "caches"
    token = get_secret("GITHUB_TOKEN")
    github_cache_path = cache_dir / "github.json"
    version_cache_path = cache_dir / "deps_versions.json"
    advisory_cache_path = cache_dir / "deps_advisories.json"
    github_cache, version_cache, advisory_cache = load_json(github_cache_path), load_json(version_cache_path), load_json(advisory_cache_path)
    github_session = requests.Session()
    if token:
        github_session.headers.update(github_headers(token))
    else:
        github_session.headers.update({"Accept": "application/vnd.github+json", "User-Agent": "maturity-tool-dependency-vulnerabilities", "X-GitHub-Api-Version": GITHUB_API_VERSION})
    deps_session = requests.Session()
    deps_session.headers.update({"Accept": "application/json", "User-Agent": "maturity-tool-dependency-vulnerabilities"})
    repos = [args.repo] if args.repo else list_repos(github_session, args.owner, args.max_repos)
    if args.max_repos is not None:
        repos = repos[: args.max_repos]
    repo_rows, vulnerability_data = [], []
    for repo in repos:
        LOGGER.info("Collecting dependency vulnerabilities for %s/%s", args.owner, repo)
        row, vulnerabilities = analyze_repo(github_session, args.owner, repo, github_cache=github_cache, github_cache_path=github_cache_path, version_cache=version_cache, version_cache_path=version_cache_path, advisory_cache=advisory_cache, advisory_cache_path=advisory_cache_path, refresh_cache=args.refresh_cache, delay_seconds=args.request_delay_seconds)
        repo_rows.append(row)
        vulnerability_data.extend(vulnerabilities)
    summary = {
        "owner": args.owner,
        "repo": args.repo,
        "repos_scanned": len(repo_rows),
        "repos_with_supported_lockfiles": sum(bool(row["lockfiles"]) for row in repo_rows),
        "repos_with_vulnerabilities": len({row["repo"] for row in vulnerability_data}),
        "vulnerabilities": len(vulnerability_data),
        "by_severity": {severity: sum(row["severity"] == severity for row in vulnerability_data) for severity in ("critical", "high", "medium", "low", "unknown")},
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "deps_api": "v3alpha/versionbatch",
    }
    write_csv(output_dir / "repo_dependency_vulnerabilities.csv", repo_rows)
    save_json(output_dir / "repo_dependency_vulnerabilities.json", repo_rows)
    write_csv(output_dir / "dependency_vulnerabilities.csv", vulnerability_data)
    save_json(output_dir / "dependency_vulnerabilities.json", vulnerability_data)
    save_json(output_dir / "summary.json", summary)
    LOGGER.info("Wrote dependency vulnerability experiment to %s (repos=%s, vulnerabilities=%s)", output_dir, summary["repos_scanned"], summary["vulnerabilities"])


if __name__ == "__main__":
    main()
