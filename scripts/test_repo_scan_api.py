import argparse
import os
from pathlib import Path
import sys
import time
from typing import Any, Optional

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
        if len(preview) > 1000:
            preview = preview[:1000] + "..."
        print(preview)
    except Exception:
        text = response.text
        if len(text) > 1000:
            text = text[:1000] + "..."
        print(text)


def request_post_json(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    label: str,
) -> Optional[requests.Response]:
    try:
        resp = session.post(url, json=payload, timeout=30)
        print_result(label, resp)
        return resp
    except Exception as exc:
        print(f"[ERROR] {label}: {exc}")
        return None


def request_get(session: requests.Session, url: str, label: str) -> Optional[requests.Response]:
    try:
        resp = session.get(url, timeout=30)
        print_result(label, resp)
        return resp
    except Exception as exc:
        print(f"[ERROR] {label}: {exc}")
        return None


def build_repo_url(owner: str | None, repo: str | None) -> str | None:
    if owner and repo:
        return f"https://github.com/{owner}/{repo}"
    return None


def parse_json_response(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        return response.json()
    except Exception as exc:
        raise SystemExit(f"{label} did not return JSON: {exc}")


def wait_for_scan(
    session: requests.Session,
    status_url: str,
    *,
    scan_id: int,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    print(
        f"[WAIT] polling scan {scan_id} every {poll_seconds}s for up to {timeout_seconds}s"
    )
    start = time.monotonic()
    while True:
        try:
            response = session.get(status_url, timeout=30)
        except Exception as exc:
            raise SystemExit(f"[WAIT] scan {scan_id} status request failed: {exc}")

        if not response.ok:
            print_result(f"scan status {scan_id}", response)
            raise SystemExit(f"[WAIT] scan {scan_id} status request failed with {response.status_code}")

        data = parse_json_response(response, f"scan status {scan_id}")
        status = data.get("status")
        elapsed = int(time.monotonic() - start)
        print(f"[WAIT] scan {scan_id} status={status} elapsed={elapsed}s")

        if status in {"completed", "failed"}:
            print(f"[WAIT] result_url={data.get('result_url')}")
            return data

        if elapsed >= timeout_seconds:
            raise SystemExit(f"[WAIT] timed out after {timeout_seconds}s waiting for scan {scan_id}")

        time.sleep(poll_seconds)


def main() -> None:
    load_dotenv(repo_root / ".env")
    parser = argparse.ArgumentParser(description="Test the ad hoc repo scan API flow.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--repo-url", help="Repository URL to validate and scan")
    parser.add_argument("--owner", help="GitHub owner/org used to build a GitHub repo URL if --repo-url is omitted")
    parser.add_argument("--repo", help="GitHub repo name used to build a GitHub repo URL if --repo-url is omitted")
    parser.add_argument("--wait-for-scan", action="store_true", help="Poll scan status until completion or failure")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval when --wait-for-scan is used (default: 5)")
    parser.add_argument("--timeout-seconds", type=float, default=300.0, help="Timeout when --wait-for-scan is used (default: 300)")
    args = parser.parse_args()

    api_key = load_api_key()

    repo_url = args.repo_url or build_repo_url(args.owner, args.repo)
    if not repo_url:
        raise SystemExit("Provide --repo-url or both --owner and --repo.")

    base_url = args.base_url.rstrip("/")
    session = requests.Session()
    session.headers.update(build_headers(api_key))
    payload = {"repo_url": repo_url}

    validate_resp = request_post_json(
        session,
        f"{base_url}/repo-scans/validate",
        payload,
        f"validate repo scan {repo_url}",
    )
    if not validate_resp or not validate_resp.ok:
        raise SystemExit("Repo scan validation failed.")
    validate_data = parse_json_response(validate_resp, "validate repo scan")
    if not validate_data.get("valid"):
        raise SystemExit(f"Repo URL is invalid: {validate_data.get('error')}")
    if not validate_data.get("accessible"):
        raise SystemExit(f"Repo URL is not accessible: {validate_data.get('error')}")
    if not validate_data.get("scan_supported"):
        raise SystemExit(f"Repo URL is valid but scanning is not supported: {validate_data.get('error')}")

    create_resp = request_post_json(
        session,
        f"{base_url}/repo-scans",
        payload,
        f"create repo scan {repo_url}",
    )
    if not create_resp or not create_resp.ok:
        raise SystemExit("Repo scan creation failed.")
    create_data = parse_json_response(create_resp, "create repo scan")

    scan_id = create_data.get("scan_id")
    status_url = create_data.get("status_url")
    result_url = create_data.get("result_url")
    if not scan_id or not status_url:
        raise SystemExit("Repo scan creation did not return scan_id/status_url.")

    print(f"[INFO] scan_id={scan_id}")
    print(f"[INFO] status_url={status_url}")
    print(f"[INFO] result_url={result_url}")

    status_resp = request_get(session, status_url, f"scan status {scan_id}")
    if not status_resp or not status_resp.ok:
        raise SystemExit("Initial repo scan status request failed.")
    status_data = parse_json_response(status_resp, f"scan status {scan_id}")

    if args.wait_for_scan:
        final_data = wait_for_scan(
            session,
            status_url,
            scan_id=int(scan_id),
            poll_seconds=args.poll_seconds,
            timeout_seconds=args.timeout_seconds,
        )
        if final_data.get("status") == "failed":
            raise SystemExit(f"Scan failed: {final_data.get('error_message')}")
    else:
        print(f"[INFO] current_status={status_data.get('status')}")


if __name__ == "__main__":
    main()
