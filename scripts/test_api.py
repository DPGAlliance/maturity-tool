import argparse
import os
from typing import Optional

import requests
from dotenv import load_dotenv

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


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


def main():
    load_dotenv(os.path.join(repo_root, ".env"))
    parser = argparse.ArgumentParser(description="Test the Maturity Tool API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--owner", help="GitHub owner/org")
    parser.add_argument("--repo", help="Repo name")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY is required in .env or environment")

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
