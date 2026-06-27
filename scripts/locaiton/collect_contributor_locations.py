import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import requests
from dotenv import load_dotenv
from sqlalchemy import distinct, func, select, union_all

from storage.db import get_session, init_db
from storage.logging_config import configure_logging
from storage.models import Commit, Issue, PullRequest, Repo
from storage.secrets import get_secret


LOGGER = logging.getLogger("location_experiment")
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".cache" / "location"
GITHUB_USERS_API = "https://api.github.com/users/{login}"
NOMINATIM_SEARCH_API = "https://nominatim.openstreetmap.org/search"
UNUSABLE_LOCATION_TOKENS = {
    "",
    "-",
    "earth",
    "everywhere",
    "global",
    "internet",
    "mars",
    "planet earth",
    "remote",
    "somewhere",
    "worldwide",
}
ACTIVITY_WEIGHTS = {
    "commits": 1.0,
    "issues_authored": 2.0,
    "prs_authored": 3.0,
    "issue_first_comments": 1.0,
    "pr_first_comments": 1.5,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Experimentally collect contributor location signals for an owner or repo.",
    )
    parser.add_argument("--owner", required=True, help="GitHub owner/org to analyze")
    parser.add_argument("--repo", help="Optional repo name to limit the analysis")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Root directory for outputs and caches (default: .cache/location)",
    )
    parser.add_argument(
        "--max-users",
        type=int,
        help="Optional limit after sorting contributors by activity score",
    )
    parser.add_argument(
        "--skip-geocode",
        action="store_true",
        help="Skip geocoding and only collect GitHub profile location strings",
    )
    parser.add_argument(
        "--refresh-github-cache",
        action="store_true",
        help="Ignore cached GitHub user profiles and refetch them",
    )
    parser.add_argument(
        "--refresh-geocode-cache",
        action="store_true",
        help="Ignore cached geocoding results and refetch them",
    )
    parser.add_argument(
        "--github-delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay between uncached GitHub profile requests",
    )
    parser.add_argument(
        "--geocode-delay-seconds",
        type=float,
        default=1.0,
        help="Delay between uncached geocoding requests (default: 1.0)",
    )
    parser.add_argument(
        "--geocoder-user-agent",
        default="maturity-tool-location-experiment/1.0",
        help="User-Agent for Nominatim geocoding requests",
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


def isoformat_or_none(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).isoformat()


def min_ts(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return left if left <= right else right


def max_ts(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return left if left >= right else right


def build_scope_filters(owner: str, repo: str | None) -> list[Any]:
    filters: list[Any] = [Repo.owner == owner]
    if repo:
        filters.append(Repo.name == repo)
    return filters


def login_present(column) -> Any:
    return column.is_not(None), column != ""


def fetch_contributor_activity(session, owner: str, repo: str | None) -> list[dict[str, Any]]:
    scope_filters = build_scope_filters(owner, repo)
    contributors: dict[str, dict[str, Any]] = {}

    def ensure_contributor(login: str) -> dict[str, Any]:
        if login not in contributors:
            contributors[login] = {
                "login": login,
                "commits": 0,
                "issues_authored": 0,
                "prs_authored": 0,
                "issue_first_comments": 0,
                "pr_first_comments": 0,
                "repos_touched": 0,
                "first_seen": None,
                "last_seen": None,
            }
        return contributors[login]

    def merge_rows(rows, count_field: str) -> None:
        for row in rows:
            login = row["login"]
            contributor = ensure_contributor(login)
            contributor[count_field] = int(row["count"] or 0)
            contributor["first_seen"] = min_ts(contributor["first_seen"], row["first_seen"])
            contributor["last_seen"] = max_ts(contributor["last_seen"], row["last_seen"])

    commit_rows = session.execute(
        select(
            Commit.author_login.label("login"),
            func.count().label("count"),
            func.min(Commit.authored_date).label("first_seen"),
            func.max(Commit.authored_date).label("last_seen"),
        )
        .join(Repo, Repo.id == Commit.repo_id)
        .where(*scope_filters, *login_present(Commit.author_login))
        .group_by(Commit.author_login)
    ).mappings()
    merge_rows(commit_rows, "commits")

    issue_rows = session.execute(
        select(
            Issue.author_login.label("login"),
            func.count().label("count"),
            func.min(Issue.created_at).label("first_seen"),
            func.max(Issue.created_at).label("last_seen"),
        )
        .join(Repo, Repo.id == Issue.repo_id)
        .where(*scope_filters, *login_present(Issue.author_login))
        .group_by(Issue.author_login)
    ).mappings()
    merge_rows(issue_rows, "issues_authored")

    pr_rows = session.execute(
        select(
            PullRequest.author_login.label("login"),
            func.count().label("count"),
            func.min(PullRequest.created_at).label("first_seen"),
            func.max(PullRequest.created_at).label("last_seen"),
        )
        .join(Repo, Repo.id == PullRequest.repo_id)
        .where(*scope_filters, *login_present(PullRequest.author_login))
        .group_by(PullRequest.author_login)
    ).mappings()
    merge_rows(pr_rows, "prs_authored")

    issue_comment_rows = session.execute(
        select(
            Issue.first_comment_author.label("login"),
            func.count().label("count"),
            func.min(Issue.first_comment_created_at).label("first_seen"),
            func.max(Issue.first_comment_created_at).label("last_seen"),
        )
        .join(Repo, Repo.id == Issue.repo_id)
        .where(*scope_filters, *login_present(Issue.first_comment_author))
        .group_by(Issue.first_comment_author)
    ).mappings()
    merge_rows(issue_comment_rows, "issue_first_comments")

    pr_comment_rows = session.execute(
        select(
            PullRequest.first_comment_author.label("login"),
            func.count().label("count"),
            func.min(PullRequest.first_comment_created_at).label("first_seen"),
            func.max(PullRequest.first_comment_created_at).label("last_seen"),
        )
        .join(Repo, Repo.id == PullRequest.repo_id)
        .where(*scope_filters, *login_present(PullRequest.first_comment_author))
        .group_by(PullRequest.first_comment_author)
    ).mappings()
    merge_rows(pr_comment_rows, "pr_first_comments")

    repo_sources = [
        select(Commit.author_login.label("login"), Commit.repo_id.label("repo_id"))
        .join(Repo, Repo.id == Commit.repo_id)
        .where(*scope_filters, *login_present(Commit.author_login)),
        select(Issue.author_login.label("login"), Issue.repo_id.label("repo_id"))
        .join(Repo, Repo.id == Issue.repo_id)
        .where(*scope_filters, *login_present(Issue.author_login)),
        select(PullRequest.author_login.label("login"), PullRequest.repo_id.label("repo_id"))
        .join(Repo, Repo.id == PullRequest.repo_id)
        .where(*scope_filters, *login_present(PullRequest.author_login)),
        select(Issue.first_comment_author.label("login"), Issue.repo_id.label("repo_id"))
        .join(Repo, Repo.id == Issue.repo_id)
        .where(*scope_filters, *login_present(Issue.first_comment_author)),
        select(PullRequest.first_comment_author.label("login"), PullRequest.repo_id.label("repo_id"))
        .join(Repo, Repo.id == PullRequest.repo_id)
        .where(*scope_filters, *login_present(PullRequest.first_comment_author)),
    ]
    repo_union = union_all(*repo_sources).subquery()
    repo_count_rows = session.execute(
        select(
            repo_union.c.login.label("login"),
            func.count(distinct(repo_union.c.repo_id)).label("repos_touched"),
        ).group_by(repo_union.c.login)
    ).mappings()
    for row in repo_count_rows:
        contributor = ensure_contributor(row["login"])
        contributor["repos_touched"] = int(row["repos_touched"] or 0)

    rows = []
    for contributor in contributors.values():
        contributor["activity_events_total"] = (
            contributor["commits"]
            + contributor["issues_authored"]
            + contributor["prs_authored"]
            + contributor["issue_first_comments"]
            + contributor["pr_first_comments"]
        )
        contributor["activity_score"] = round(
            contributor["commits"] * ACTIVITY_WEIGHTS["commits"]
            + contributor["issues_authored"] * ACTIVITY_WEIGHTS["issues_authored"]
            + contributor["prs_authored"] * ACTIVITY_WEIGHTS["prs_authored"]
            + contributor["issue_first_comments"] * ACTIVITY_WEIGHTS["issue_first_comments"]
            + contributor["pr_first_comments"] * ACTIVITY_WEIGHTS["pr_first_comments"],
            2,
        )
        contributor["first_seen"] = isoformat_or_none(contributor["first_seen"])
        contributor["last_seen"] = isoformat_or_none(contributor["last_seen"])
        rows.append(contributor)

    rows.sort(
        key=lambda row: (
            -row["activity_score"],
            -row["activity_events_total"],
            row["login"],
        )
    )
    return rows


def github_profile_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "maturity-tool-location-experiment",
    }


def response_snippet(response: requests.Response, limit: int = 300) -> str:
    text = (response.text or "").strip()
    return text[:limit]


def fetch_github_profile(
    session: requests.Session,
    login: str,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> dict[str, Any]:
    if not refresh_cache and login in cache:
        return cache[login].get("data") or {}

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    response = session.get(GITHUB_USERS_API.format(login=login))
    if response.status_code == 404:
        LOGGER.warning("GitHub profile not found for login=%s", login)
        cache[login] = {"fetched_at": pd.Timestamp.utcnow().isoformat(), "data": {}}
        save_json_cache(cache_path, cache)
        return {}
    if not response.ok:
        raise RuntimeError(
            f"GET {response.url} failed: {response.status_code} {response_snippet(response)}"
        )

    data = response.json()
    cache[login] = {"fetched_at": pd.Timestamp.utcnow().isoformat(), "data": data}
    save_json_cache(cache_path, cache)
    return data


def geocoder_headers(user_agent: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": user_agent,
    }


def location_cache_key(raw_location: str) -> str:
    return " ".join(raw_location.strip().lower().split())


def looks_unusable_location(raw_location: str | None) -> bool:
    if not raw_location:
        return True
    normalized = location_cache_key(raw_location)
    if normalized in UNUSABLE_LOCATION_TOKENS:
        return True
    return any(token in normalized for token in ["remote", "distributed", "worldwide", "global"])


def first_present(mapping: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value:
            return value
    return None


def normalize_geocode_result(raw_location: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    if looks_unusable_location(raw_location):
        return {
            "status": "skipped_unusable",
            "raw_location": raw_location,
            "country": None,
            "country_code": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "confidence": "none",
            "display_name": None,
            "ambiguous": False,
        }

    if not payload:
        return {
            "status": "no_match",
            "raw_location": raw_location,
            "country": None,
            "country_code": None,
            "region": None,
            "city": None,
            "latitude": None,
            "longitude": None,
            "confidence": "none",
            "display_name": None,
            "ambiguous": False,
        }

    countries = {
        (item.get("address") or {}).get("country_code")
        for item in payload
        if (item.get("address") or {}).get("country_code")
    }
    first = payload[0]
    address = first.get("address") or {}
    city = first_present(address, ["city", "town", "village", "municipality", "hamlet"])
    region = first_present(address, ["state", "region", "county"])
    country = address.get("country")
    country_code = address.get("country_code")
    ambiguous = len(countries) > 1
    if country and city and not ambiguous:
        confidence = "high"
    elif country and not ambiguous:
        confidence = "medium"
    elif country:
        confidence = "low"
    else:
        confidence = "none"

    return {
        "status": "ok",
        "raw_location": raw_location,
        "country": country,
        "country_code": country_code.upper() if country_code else None,
        "region": region,
        "city": city,
        "latitude": first.get("lat"),
        "longitude": first.get("lon"),
        "confidence": confidence,
        "display_name": first.get("display_name"),
        "ambiguous": ambiguous,
    }


def skipped_geocode_result(raw_location: str | None) -> dict[str, Any]:
    return {
        "status": "skipped",
        "raw_location": raw_location,
        "country": None,
        "country_code": None,
        "region": None,
        "city": None,
        "latitude": None,
        "longitude": None,
        "confidence": "none",
        "display_name": None,
        "ambiguous": False,
    }


def geocode_location(
    session: requests.Session,
    raw_location: str | None,
    *,
    cache: dict[str, Any],
    cache_path: Path,
    refresh_cache: bool,
    delay_seconds: float,
) -> dict[str, Any]:
    if not raw_location:
        return normalize_geocode_result("", [])

    key = location_cache_key(raw_location)
    if not refresh_cache and key in cache:
        return cache[key]

    if looks_unusable_location(raw_location):
        result = normalize_geocode_result(raw_location, [])
        cache[key] = result
        save_json_cache(cache_path, cache)
        return result

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    response = session.get(
        NOMINATIM_SEARCH_API,
        params={
            "q": raw_location,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 3,
        },
    )
    if not response.ok:
        raise RuntimeError(
            f"GET {response.url} failed: {response.status_code} {response_snippet(response)}"
        )
    payload = response.json()
    result = normalize_geocode_result(raw_location, payload)
    cache[key] = result
    save_json_cache(cache_path, cache)
    return result


def enrich_contributors(
    contributors: list[dict[str, Any]],
    *,
    github_session: requests.Session,
    github_cache: dict[str, Any],
    github_cache_path: Path,
    refresh_github_cache: bool,
    github_delay_seconds: float,
    geocode_session: requests.Session,
    geocode_cache: dict[str, Any],
    geocode_cache_path: Path,
    refresh_geocode_cache: bool,
    geocode_delay_seconds: float,
    skip_geocode: bool,
) -> list[dict[str, Any]]:
    enriched = []
    total = len(contributors)
    for index, contributor in enumerate(contributors, start=1):
        login = contributor["login"]
        LOGGER.info("Enriching contributor %s/%s login=%s", index, total, login)
        profile = fetch_github_profile(
            github_session,
            login,
            cache=github_cache,
            cache_path=github_cache_path,
            refresh_cache=refresh_github_cache,
            delay_seconds=github_delay_seconds,
        )
        raw_location = profile.get("location")
        geocode = (
            skipped_geocode_result(raw_location)
            if skip_geocode
            else geocode_location(
                geocode_session,
                raw_location,
                cache=geocode_cache,
                cache_path=geocode_cache_path,
                refresh_cache=refresh_geocode_cache,
                delay_seconds=geocode_delay_seconds,
            )
        )
        enriched.append(
            {
                **contributor,
                "github_name": profile.get("name"),
                "github_company": profile.get("company"),
                "github_blog": profile.get("blog"),
                "github_public_email": profile.get("email"),
                "github_profile_url": profile.get("html_url"),
                "github_profile_location": raw_location,
                "location_status": geocode.get("status"),
                "location_confidence": geocode.get("confidence"),
                "location_country": geocode.get("country"),
                "location_country_code": geocode.get("country_code"),
                "location_region": geocode.get("region"),
                "location_city": geocode.get("city"),
                "location_latitude": geocode.get("latitude"),
                "location_longitude": geocode.get("longitude"),
                "location_display_name": geocode.get("display_name"),
                "location_ambiguous": geocode.get("ambiguous"),
            }
        )
    return enriched


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


def build_summaries(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    df = pd.DataFrame(rows)
    if df.empty:
        summary = {
            "contributors": 0,
            "contributors_with_profile_location": 0,
            "contributors_with_country": 0,
            "contributors_with_city": 0,
        }
        return [], [], summary

    summary = {
        "contributors": int(len(df)),
        "contributors_with_profile_location": int(df["github_profile_location"].fillna("").ne("").sum()),
        "contributors_with_country": int(df["location_country"].fillna("").ne("").sum()),
        "contributors_with_city": int(df["location_city"].fillna("").ne("").sum()),
    }

    country_df = df[df["location_country"].fillna("").ne("")]
    if not country_df.empty:
        country_summary = (
            country_df.groupby(["location_country", "location_country_code"], dropna=False)
            .agg(
                contributors=("login", "nunique"),
                activity_score=("activity_score", "sum"),
                activity_events_total=("activity_events_total", "sum"),
                commits=("commits", "sum"),
                issues_authored=("issues_authored", "sum"),
                prs_authored=("prs_authored", "sum"),
                issue_first_comments=("issue_first_comments", "sum"),
                pr_first_comments=("pr_first_comments", "sum"),
            )
            .reset_index()
            .sort_values(["activity_score", "contributors"], ascending=[False, False])
        )
        country_rows = country_summary.to_dict("records")
    else:
        country_rows = []

    city_df = df[
        df["location_country"].fillna("").ne("")
        & df["location_city"].fillna("").ne("")
    ]
    if not city_df.empty:
        city_summary = (
            city_df.groupby(
                ["location_country", "location_country_code", "location_region", "location_city"],
                dropna=False,
            )
            .agg(
                contributors=("login", "nunique"),
                activity_score=("activity_score", "sum"),
                activity_events_total=("activity_events_total", "sum"),
            )
            .reset_index()
            .sort_values(["activity_score", "contributors"], ascending=[False, False])
        )
        city_rows = city_summary.to_dict("records")
    else:
        city_rows = []

    return country_rows, city_rows, summary


def main() -> None:
    configure_logging()
    load_dotenv(REPO_ROOT / ".env")
    args = parse_args()

    init_db()
    token = get_secret("GITHUB_TOKEN", required=True)
    output_root = Path(args.output_root)
    output_dir = output_root / scope_slug(args.owner, args.repo)
    cache_dir = output_root / "caches"
    ensure_dir(output_dir)
    ensure_dir(cache_dir)

    github_cache_path = cache_dir / "github_users.json"
    geocode_cache_path = cache_dir / "geocoding.json"
    github_cache = load_json_cache(github_cache_path)
    geocode_cache = load_json_cache(geocode_cache_path)

    github_session = requests.Session()
    github_session.headers.update(github_profile_headers(token))
    geocode_session = requests.Session()
    geocode_session.headers.update(geocoder_headers(args.geocoder_user_agent))

    session = get_session()
    try:
        contributors = fetch_contributor_activity(session, args.owner, args.repo)
    finally:
        session.close()

    if args.max_users:
        contributors = contributors[: args.max_users]

    LOGGER.info("Collected %s contributors for scope owner=%s repo=%s", len(contributors), args.owner, args.repo)
    enriched_rows = enrich_contributors(
        contributors,
        github_session=github_session,
        github_cache=github_cache,
        github_cache_path=github_cache_path,
        refresh_github_cache=args.refresh_github_cache,
        github_delay_seconds=args.github_delay_seconds,
        geocode_session=geocode_session,
        geocode_cache=geocode_cache,
        geocode_cache_path=geocode_cache_path,
        refresh_geocode_cache=args.refresh_geocode_cache,
        geocode_delay_seconds=args.geocode_delay_seconds,
        skip_geocode=args.skip_geocode,
    )

    country_rows, city_rows, summary = build_summaries(enriched_rows)
    summary.update(
        {
            "owner": args.owner,
            "repo": args.repo,
            "max_users": args.max_users,
            "skip_geocode": args.skip_geocode,
            "generated_at": pd.Timestamp.utcnow().isoformat(),
        }
    )

    write_csv(output_dir / "contributors.csv", enriched_rows)
    write_json(output_dir / "contributors.json", enriched_rows)
    write_csv(output_dir / "country_summary.csv", country_rows)
    write_csv(output_dir / "city_summary.csv", city_rows)
    write_json(output_dir / "summary.json", summary)

    LOGGER.info(
        "Wrote location experiment outputs to %s (contributors=%s, country_coverage=%s, city_coverage=%s)",
        output_dir,
        summary["contributors"],
        summary["contributors_with_country"],
        summary["contributors_with_city"],
    )


if __name__ == "__main__":
    main()
