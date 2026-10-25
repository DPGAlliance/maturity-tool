import argparse
import json
from pathlib import Path
import sys
from typing import Any

import requests
from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from storage.secrets import get_secret


DEFAULT_CASES_FILE = repo_root / "scripts" / "repo_validation_cases.json"
COMPARISON_FIELDS = [
    "provider",
    "provider_family",
    "valid",
    "accessible",
    "scan_supported",
    "result_class",
]


def load_api_key() -> str:
    api_key = get_secret("API_KEY")
    if api_key:
        return api_key
    fallback_path = repo_root / "secrets" / "api_key"
    if fallback_path.exists():
        return fallback_path.read_text(encoding="utf-8").strip()
    raise SystemExit("API_KEY is required. Set API_KEY or API_KEY_FILE, or create secrets/api_key.")


def build_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def load_case_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Cases file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Cases file is not valid JSON: {path} ({exc})") from exc


def select_cases(data: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    cases = data.get("cases") or []
    if args.repo_url:
        single_case = {
            "id": "ad-hoc",
            "scenario": "ad-hoc",
            "label": args.repo_url,
            "repo_url": args.repo_url,
            "expect": {},
        }
        return [single_case]

    if not args.scenario or args.scenario == "all":
        return cases
    selected = [case for case in cases if case.get("scenario") == args.scenario]
    if not selected:
        raise SystemExit(f"No cases found for scenario: {args.scenario}")
    return selected


def post_json(session: requests.Session, url: str, payload: dict[str, Any]) -> requests.Response:
    return session.post(url, json=payload, timeout=30)


def parse_json_response(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        return response.json()
    except Exception as exc:
        raise SystemExit(f"{label} did not return JSON: {exc}\n{response.text}")


def compare_expectations(expect: dict[str, Any], actual: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches = []
    for field, expected in expect.items():
        actual_value = actual.get(field)
        if actual_value != expected:
            mismatches.append(f"{field}: expected={expected!r} actual={actual_value!r}")
    return (len(mismatches) == 0, mismatches)


def should_create_scan(case: dict[str, Any], validate_data: dict[str, Any], create_scan_flag: bool) -> bool:
    if not create_scan_flag:
        return False
    if case.get("create_scan") is False:
        return False
    return bool(validate_data.get("valid") and validate_data.get("accessible") and validate_data.get("scan_supported"))


def summarize(results: list[dict[str, Any]]) -> None:
    print("\nSummary:")
    print(f"- total cases: {len(results)}")
    print(f"- passed: {sum(1 for item in results if item['passed'])}")
    print(f"- failed: {sum(1 for item in results if not item['passed'])}")

    by_provider: dict[str, int] = {}
    by_result_class: dict[str, int] = {}
    for item in results:
        data = item["validate_data"]
        provider = data.get("provider") or "none"
        result_class = data.get("result_class") or "unknown"
        by_provider[provider] = by_provider.get(provider, 0) + 1
        by_result_class[result_class] = by_result_class.get(result_class, 0) + 1

    print("- by provider:")
    for provider, count in sorted(by_provider.items(), key=lambda item: (-item[1], item[0])):
        print(f"  - {provider}: {count}")

    print("- by result class:")
    for result_class, count in sorted(by_result_class.items(), key=lambda item: (-item[1], item[0])):
        print(f"  - {result_class}: {count}")


def main() -> None:
    load_dotenv(repo_root / ".env")
    parser = argparse.ArgumentParser(description="Scenario-driven tester for provider-aware repo validation and optional scan creation.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--repo-url", help="Single repository URL to validate without using the case file")
    parser.add_argument("--cases-file", default=str(DEFAULT_CASES_FILE), help=f"JSON case file (default: {DEFAULT_CASES_FILE})")
    parser.add_argument("--scenario", default="all", help="Scenario name from the case file, or 'all' (default: all)")
    parser.add_argument("--create-scan", action="store_true", help="Also call POST /repo-scans for supported repos")
    parser.add_argument("--show-summary", action="store_true", help="Print aggregate counts after the run")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any case fails its expected outcome")
    args = parser.parse_args()

    api_key = load_api_key()
    session = requests.Session()
    session.headers.update(build_headers(api_key))
    base_url = args.base_url.rstrip("/")

    case_data = load_case_file(Path(args.cases_file)) if not args.repo_url else {"cases": []}
    cases = select_cases(case_data, args)
    results: list[dict[str, Any]] = []

    print(f"[INFO] case_count={len(cases)}")
    print("[INFO] auth_mode=api-key client-side; provider tokens are evaluated server-side")
    print("[INFO] validation and create-scan calls will generate telemetry rows in repo_scan_request_logs")

    for case in cases:
        repo_url = case["repo_url"]
        label = case.get("label") or case.get("id") or repo_url
        payload = {"repo_url": repo_url}
        validate_resp = post_json(session, f"{base_url}/repo-scans/validate", payload)
        validate_data = parse_json_response(validate_resp, f"validate {label}")

        expect = case.get("expect") or {}
        passed, mismatches = compare_expectations(expect, validate_data)

        print(f"\n[{'PASS' if passed else 'FAIL'}] {label}")
        print(f"  scenario={case.get('scenario')} repo_url={repo_url}")
        print(
            "  actual="
            f"provider={validate_data.get('provider')} family={validate_data.get('provider_family')} "
            f"valid={validate_data.get('valid')} accessible={validate_data.get('accessible')} "
            f"supported={validate_data.get('scan_supported')} confidence={validate_data.get('confidence')} "
            f"result_class={validate_data.get('result_class')}"
        )
        if expect:
            print(
                "  expect="
                + ", ".join(
                    f"{field}={expect[field]!r}" for field in COMPARISON_FIELDS if field in expect
                )
            )
        if mismatches:
            for mismatch in mismatches:
                print(f"  mismatch: {mismatch}")
        if validate_data.get("error"):
            print(f"  error={validate_data.get('error')}")

        create_data = None
        if should_create_scan(case, validate_data, args.create_scan):
            create_resp = post_json(session, f"{base_url}/repo-scans", payload)
            create_data = parse_json_response(create_resp, f"create scan {label}")
            print(
                "  create_scan="
                f"status={create_resp.status_code} scan_id={create_data.get('scan_id')} "
                f"job_status={create_data.get('status')} result_url={create_data.get('result_url')}"
            )

        results.append(
            {
                "label": label,
                "scenario": case.get("scenario"),
                "repo_url": repo_url,
                "passed": passed,
                "mismatches": mismatches,
                "validate_data": validate_data,
                "create_data": create_data,
            }
        )

    if args.show_summary:
        summarize(results)

    if args.strict and any(not item["passed"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
