import argparse
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROMPTS_DIR = os.path.join(REPO_ROOT, "prompts")

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_HISTORY_LIMIT = 5
DEFAULT_SUMMARY_MAX_AGE_DAYS = 30

DRIFT_THRESHOLDS = {
    "issue_closure_ratio_90d": {"type": "abs", "value": 0.05},
    "median_time_to_first_response_hours": {"type": "abs", "value": 24},
    "median_time_to_close_days": {"type": "abs", "value": 2},
    "median_pr_merge_time_days": {"type": "abs", "value": 2},
    "bus_factor": {"type": "abs", "value": 1},
    "hhi": {"type": "abs", "value": 150},
    "new_contributors": {"type": "rel", "value": 0.1, "abs": 5},
    "active_core_contributors": {"type": "rel", "value": 0.1, "abs": 3},
    "total_commits": {"type": "rel", "value": 0.1, "abs": 20},
    "total_contributors": {"type": "rel", "value": 0.1, "abs": 5},
    "staleness_days": {"type": "abs", "value": 7},
    "backlog_size": {"type": "rel", "value": 0.1, "abs": 10},
    "good_first_issue_velocity_90d": {"type": "abs", "value": 3},
    "release_count": {"type": "rel", "value": 0.1, "abs": 2},
    "total_downloads": {"type": "rel", "value": 0.1, "abs": 100},
}

LOGGER = logging.getLogger("summarizer")
if not LOGGER.handlers:
    LOGGER.setLevel(logging.INFO)
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.INFO)
    _formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    _handler.setFormatter(_formatter)
    LOGGER.addHandler(_handler)



def load_prompt(path: str) -> Tuple[str, Optional[str]]:
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    version = None
    for line in content.splitlines()[:5]:
        if line.lower().startswith("prompt-version:"):
            version = line.split(":", 1)[1].strip()
            break
    return content, version


def api_headers(api_key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def get_json(session: requests.Session, url: str) -> Any:
    resp = session.get(url, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"GET {url} failed: {resp.status_code} {resp.text}")
    return resp.json()


def post_json(session: requests.Session, url: str, payload: dict) -> Any:
    resp = session.post(url, json=payload, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"POST {url} failed: {resp.status_code} {resp.text}")
    return resp.json()







def normalize_time_range(value: Optional[str]) -> str:
    "DUDE. THIS IS NOT NEEDED."
    if not value:
        return "all"
    lowered = value.lower().strip()
    if lowered in {"all", "all time", "all-time"}:
        return "all"
    return lowered







def select_all_time_run(metrics_history: dict, latest_metrics: dict) -> dict:
    run = latest_metrics.get("run", {})
    if normalize_time_range(run.get("time_range")) == "all":
        return latest_metrics

    for entry in metrics_history.get("runs", []):
        if normalize_time_range(entry.get("run", {}).get("time_range")) == "all":
            return entry

    return latest_metrics


def get_latest_summary(session: requests.Session, base_url: str, owner: str, repo: str) -> Optional[dict]:
    try:
        summaries = get_json(
            session,
            f"{base_url}/repos/{owner}/{repo}/summaries?limit=1",
        )
        if summaries:
            return summaries[0]
    except RuntimeError:
        return None
    return None


def get_org_latest_summary(session: requests.Session, base_url: str, owner: str) -> Optional[dict]:
    try:
        summaries = get_json(
            session,
            f"{base_url}/orgs/{owner}/summaries?limit=1",
        )
        if summaries:
            return summaries[0]
    except RuntimeError:
        return None
    return None


def flatten_metrics(metrics: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    flat = {}
    for scope, entries in metrics.items():
        for name, value in entries.items():
            flat[f"{scope}.{name}"] = value
    return flat


def has_drift(latest: Dict[str, Dict[str, Any]], previous: Dict[str, Dict[str, Any]]) -> Tuple[bool, List[str]]:
    latest_flat = flatten_metrics(latest)
    previous_flat = flatten_metrics(previous)
    reasons = []

    for metric_name, config in DRIFT_THRESHOLDS.items():
        matching_latest = {k: v for k, v in latest_flat.items() if k.endswith(f".{metric_name}")}
        matching_prev = {k: v for k, v in previous_flat.items() if k.endswith(f".{metric_name}")}
        for key, latest_value in matching_latest.items():
            prev_value = matching_prev.get(key)
            if prev_value is None:
                continue
            if latest_value is None:
                continue
            try:
                latest_val = float(latest_value)
                prev_val = float(prev_value)
            except Exception:
                continue

            if config["type"] == "abs":
                if abs(latest_val - prev_val) >= config["value"]:
                    reasons.append(f"{key} changed by {latest_val - prev_val:.2f}")
            else:
                abs_threshold = config.get("abs", 0)
                rel_threshold = config.get("value", 0)
                rel_change = abs(latest_val - prev_val) / abs(prev_val) if prev_val else 1
                if abs(latest_val - prev_val) >= abs_threshold or rel_change >= rel_threshold:
                    reasons.append(f"{key} changed by {latest_val - prev_val:.2f}")

    return len(reasons) > 0, reasons


def should_summarize(
    latest_metrics: dict,
    previous_summary: Optional[dict],
    previous_metrics: Optional[dict],
    force: bool,
    max_age_days: int,
):
    if force or not previous_summary:
        return True, ["forced" if force else "no previous summary"]

    previous_created_at = pd.to_datetime(previous_summary.get("created_at"))
    if previous_created_at:
        now = datetime.now()
        LOGGER.info("Previous summary created at %s NOW: %s", previous_created_at, now)
        age_days = (now - previous_created_at).days
        if age_days >= max_age_days:
            return True, [f"summary age {age_days} days"]

    if previous_metrics:
        drift, reasons = has_drift(latest_metrics.get("metrics", {}), previous_metrics.get("metrics", {}))
        if drift:
            return True, reasons

    return False, ["no significant changes"]


def fetch_repo_description(owner: str, repo: str, token: Optional[str]) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers, timeout=30)
    if not resp.ok:
        return {}
    data = resp.json()
    return {
        "description": data.get("description"),
        "topics": data.get("topics") or [],
        "homepage": data.get("homepage"),
        "language": data.get("language"),
        "archived": data.get("archived"),
    }


def build_repo_payload(
    owner: str,
    repo: str,
    latest_metrics: dict,
    history: dict,
    description: dict,
):
    repo_key = f"{owner}/{repo}"
    return {
        "repo": repo_key,
        "run": latest_metrics.get("run"),
        "metrics": latest_metrics.get("metrics"),
        "metrics_history": history.get("runs", []),
        "description": {**description},
    }


def build_org_payload(owner: str, repos_payload: List[dict]) -> dict:
    return {
        "owner": owner,
        "repos": repos_payload,
    }


def call_openai(client: OpenAI, model: str, prompt: str, data: dict) -> str:
    rendered = prompt.replace("{{DATA}}", json.dumps(data, ensure_ascii=False))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a precise analyst."},
            {"role": "user", "content": rendered},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def summarize_repo(
    session: requests.Session,
    client: OpenAI,
    base_url: str,
    owner: str,
    repo: str,
    prompt_path: str,
    model: str,
    history_limit: int,
    max_age_days: int,
    force: bool,
    github_token: Optional[str],
    store: bool = True,
) -> Optional[str]:
    latest_metrics = get_json(session, f"{base_url}/repos/{owner}/{repo}/metrics")
    history = get_json(session, f"{base_url}/repos/{owner}/{repo}/metrics/history?limit={history_limit}")
    latest_metrics = select_all_time_run(history, latest_metrics)

    print(f"\----------- \nLatest metrics for {owner}/{repo}: {latest_metrics}")
    print(f"\------   ***_____  ----- \nHistory for {owner}/{repo}: {history}")
    print(f"\------   ***_____lkajsdlfkjalskdj lkjasdf  afsdlkja  ----- \n")

    latest_run_id = latest_metrics.get("run", {}).get("id")
    previous_summary = get_latest_summary(session, base_url, owner, repo)

    previous_metrics = None
    if previous_summary and previous_summary.get("run_id"):
        previous_metrics = get_json(
            session,
            f"{base_url}/repos/{owner}/{repo}/metrics?run_id={previous_summary['run_id']}",
        )

    should_write, reasons = should_summarize(
        latest_metrics,
        previous_summary,
        previous_metrics,
        force,
        max_age_days,
    )
    if not should_write:
        LOGGER.info("[SKIP] %s/%s: %s", owner, repo, ", ".join(reasons))
        return None

    prompt, prompt_version = load_prompt(prompt_path)
    description = fetch_repo_description(owner, repo, github_token)
    openai_payload = build_repo_payload(owner, repo, latest_metrics, history, description)
    summary_text = call_openai(client, model, prompt, openai_payload)
    butler_payload = {
                "summary_text": summary_text,
                "model": model,
                "prompt_version": prompt_version,
                "run_id": latest_run_id,
                "metadata_json": {
                    "reasons": reasons,
                    "history_limit": history_limit,
                },
            }

    if store:
        post_json(
            session,
            f"{base_url}/repos/{owner}/{repo}/summary",
            butler_payload,
        )
    else:
        LOGGER.info("[NOT STORING SUMMARY FOR] %s/%s: %s, %s", owner, repo, ", ".join(reasons), str(butler_payload))
    LOGGER.info("[OK] %s/%s: %s", owner, repo, ", ".join(reasons))
    return summary_text


def summarize_org(
    session: requests.Session,
    client: OpenAI,
    base_url: str,
    owner: str,
    prompt_path: str,
    model: str,
    history_limit: int,
    max_age_days: int,
    force: bool,
    store: bool = True,
) -> Optional[str]:
    org_metrics = get_json(session, f"{base_url}/orgs/{owner}/metrics")

    previous_summary = get_org_latest_summary(session, base_url, owner)
    previous_metrics = None
    if previous_summary and previous_summary.get("run_id"):
        previous_metrics = {"metrics": {}}  # org summaries do not map to a single run

    should_write, reasons = should_summarize(
        {"metrics": {}},
        previous_summary,
        previous_metrics,
        force,
        max_age_days,
    )
    if not should_write:
        LOGGER.info("[SKIP] org %s: %s", owner, ", ".join(reasons))
        return None

    prompt, prompt_version = load_prompt(prompt_path)
    openai_payload = build_org_payload(owner, org_metrics)
    summary_text = call_openai(client, model, prompt, openai_payload)
    butler_payload = {
                "summary_text": summary_text,
                "model": model,
                "prompt_version": prompt_version,
                "run_id": None,
                "metadata_json": {
                    "reasons": reasons,
                    "history_limit": history_limit,
                },
            }

    if store:
        post_json(
            session,
            f"{base_url}/orgs/{owner}/summary",
            butler_payload,
        )
    else:
        LOGGER.info("[NOT STORING SUMMARY FOR] org %s: %s, %s", owner, ", ".join(reasons), str(butler_payload))
    LOGGER.info("[OK] org %s: %s", owner, ", ".join(reasons))
    return summary_text


def parse_args():
    parser = argparse.ArgumentParser(description="Generate LLM summaries.")
    parser.add_argument("--repo", help="owner/name")
    parser.add_argument("--owner", help="org/owner for batch summaries")
    parser.add_argument("--force", action="store_true", help="force summary generation")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--history", type=int, default=DEFAULT_HISTORY_LIMIT)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_SUMMARY_MAX_AGE_DAYS)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--no_store", action="store_true", help="do not store the generated summaries")
    return parser.parse_args()





def main():
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    args = parse_args()

    # get api keys and validate
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise SystemExit("API_KEY is required in .env")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise SystemExit("OPENAI_API_KEY is required in .env")

    github_token = os.getenv("GITHUB_TOKEN")

    session = requests.Session()
    session.headers.update(api_headers(api_key))
    client = OpenAI(api_key=openai_key)

    repo_prompt = os.path.join(PROMPTS_DIR, "repo_summary.md")
    org_prompt = os.path.join(PROMPTS_DIR, "org_summary.md")

    if args.repo:
        owner, repo = args.repo.split("/", 1)
        summarize_repo(
            session,
            client,
            args.base_url.rstrip("/"),
            owner,
            repo,
            repo_prompt,
            args.model,
            args.history,
            args.max_age_days,
            args.force,
            github_token,
            not args.no_store, # no_store flag true means store=False, so we invert it here to pass the correct value
        )
        return

    if args.owner:
        repos = get_json(session, f"{args.base_url.rstrip('/')}/repos?owner={args.owner}")
        for repo_entry in repos:
            summarize_repo(
                session,
                client,
                args.base_url.rstrip("/"),
                repo_entry["owner"],
                repo_entry["name"],
                repo_prompt,
                args.model,
                args.history,
                args.max_age_days,
                args.force,
                github_token,
                not args.no_store, # no_store flag true means store=False, so we invert it here to pass the correct value
            )
        summarize_org(
            session,
            client,
            args.base_url.rstrip("/"),
            args.owner,
            org_prompt,
            args.model,
            args.history,
            args.max_age_days,
            args.force,
            not args.no_store, # no_store flag true means store=False, so we invert it here to pass the correct value
        )
        return

    raise SystemExit("Provide --repo owner/name or --owner org")


if __name__ == "__main__":
    main()
