import argparse
from datetime import date, datetime
from decimal import Decimal
import os

import requests
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import text

from storage.db import get_engine
from storage.logging_config import configure_logging
from storage.secrets import get_secret
from summarize import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_MODEL,
    DEFAULT_SUMMARY_MAX_AGE_DAYS,
    PROMPTS_DIR,
    REPO_ROOT,
    api_headers,
    summarize_org,
)


QUERIES_DIR = os.path.join(REPO_ROOT, "queries")


def load_query(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _jsonify_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def run_query(engine, query_name: str, params: dict) -> list[dict]:
    query_path = os.path.join(QUERIES_DIR, query_name)
    sql = load_query(query_path)
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
        return [
            {key: _jsonify_value(value) for key, value in dict(row).items()}
            for row in result.mappings().all()
        ]


def build_query_results(engine, owner: str, top_n: int) -> dict:
    repo_count_rows = run_query(engine, "org_repo_count.sql", {"owner": owner})
    top_active_repos = run_query(
        engine,
        "org_top_active_repos.sql",
        {
            "owner": owner,
            "top_n": top_n,
        },
    )
    repo_count = repo_count_rows[0]["repo_count"] if repo_count_rows else 0
    return {
        "repo_count": repo_count,
        "top_active_repos": top_active_repos,
        "top_active_window_days": 90,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test the org summary prompt against the latest stored repo metrics.",
    )
    parser.add_argument("--owner", required=True, help="Org/owner to summarize")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--history", type=int, default=DEFAULT_HISTORY_LIMIT)
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_SUMMARY_MAX_AGE_DAYS)
    parser.add_argument("--top-n", type=int, default=10, help="Top active repos to inject (default: 10)")
    parser.add_argument("--force", action="store_true", help="Force summary generation")
    parser.add_argument("--store", action="store_true", help="Store the generated org summary")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    load_dotenv(os.path.join(REPO_ROOT, ".env"))
    args = parse_args()

    api_key = get_secret("API_KEY", required=True)
    openai_key = get_secret("OPENAI_API_KEY", required=True)
    engine = get_engine()

    session = requests.Session()
    session.headers.update(api_headers(api_key))
    client = OpenAI(api_key=openai_key)
    query_results = build_query_results(engine, args.owner, args.top_n)

    summary_text = summarize_org(
        session=session,
        client=client,
        base_url=args.base_url.rstrip("/"),
        owner=args.owner,
        prompt_path=os.path.join(PROMPTS_DIR, "org_summary.md"),
        model=args.model,
        history_limit=args.history,
        max_age_days=args.max_age_days,
        force=args.force,
        store=args.store,
        query_results=query_results,
    )

    if summary_text:
        print(summary_text)
    else:
        print(f"[SKIPPED] org {args.owner}")


if __name__ == "__main__":
    main()
