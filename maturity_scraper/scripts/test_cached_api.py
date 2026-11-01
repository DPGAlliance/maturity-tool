import argparse
import os
from pathlib import Path
import sys
from typing import Optional

import requests
from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from storage.secrets import get_secret


def load_api_key() -> str:
    api_key = get_secret("API_KEY")
    if api_key:
        return api_key

    fallback_path = repo_root / "secrets" / "api_key"
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8").strip()

    raise SystemExit(
        "API_KEY is required. Set API_KEY or API_KEY_FILE, or create secrets/api_key."
    )


def build_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def print_result(label: str, response: requests.Response) -> None:
    status = response.status_code
    print(f"[{status}] {label}")
    try:
        data = response.json()
        preview = str(data)
        if len(preview) > 800:
            preview = preview[:800] + "..."
        print(preview)
    except Exception:
        text = response.text
        if len(text) > 800:
            text = text[:800] + "..."
        print(text)


def request_get(session: requests.Session, url: str, label: str) -> Optional[requests.Response]:
    try:
        resp = session.get(url, timeout=30)
        print_result(label, resp)
        return resp
    except Exception as exc:
        print(f"[ERROR] {label}: {exc}")
        return None


def main() -> None:
    load_dotenv(repo_root / ".env")
    parser = argparse.ArgumentParser(description="Test the cached/read-only Maturity Tool API endpoints.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--owner", help="GitHub owner/org")
    parser.add_argument("--repo", help="Repo name")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    api_key = load_api_key()

    base_url = args.base_url.rstrip("/")
    owner = args.owner or os.getenv("API_OWNER")
    repo = args.repo or os.getenv("API_REPO")

    session = requests.Session()
    session.headers.update(build_headers(api_key))

    if owner:
        repos_resp = request_get(
            session,
            f"{base_url}/repos?owner={owner}",
            f"repos for {owner}",
        )
        if not repo and repos_resp and repos_resp.ok:
            try:
                repos_data = repos_resp.json()
                if repos_data:
                    repo = repos_data[0]["name"]
            except Exception:
                pass
    else:
        request_get(session, f"{base_url}/repos", "repos (no owner filter)")

    if owner and repo:
        request_get(
            session,
            f"{base_url}/repos/{owner}/{repo}/metrics",
            f"metrics latest {owner}/{repo}",
        )
        request_get(
            session,
            f"{base_url}/repos/{owner}/{repo}/metrics/history?limit={args.limit}",
            f"metrics history {owner}/{repo}",
        )
        request_get(
            session,
            f"{base_url}/repos/{owner}/{repo}/summary",
            f"summary latest {owner}/{repo}",
        )
        request_get(
            session,
            f"{base_url}/repos/{owner}/{repo}/summaries?limit={args.limit}",
            f"summaries list {owner}/{repo}",
        )

    if owner:
        request_get(
            session,
            f"{base_url}/orgs/{owner}/metrics",
            f"org metrics {owner}",
        )
        request_get(
            session,
            f"{base_url}/orgs/{owner}/summary",
            f"org summary {owner}",
        )
        request_get(
            session,
            f"{base_url}/orgs/{owner}/summaries?limit={args.limit}",
            f"org summaries {owner}",
        )


if __name__ == "__main__":
    main()
