import argparse
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from maturity_tools.analyzers import CommitAnalyzer, IssuePRAnalyzer, ReleaseAnalyzer
from maturity_tools.github_call import (
    fetch_commit_page,
    fetch_governance_files,
    github_api_call,
    process_branches,
    process_commits,
    process_issues,
    process_prs,
    process_releases,
)
from maturity_tools.queries import repo_info_query
from storage.cache import (
    create_run,
    delete_cached_commits,
    get_cached_branch,
    get_cached_branches,
    get_cached_commit_count,
    get_cached_commits,
    get_cached_issues,
    get_cached_prs,
    get_cached_releases,
    get_existing_commit_oids,
    get_or_create_repo,
    is_cache_fresh,
    record_fetch,
    upsert_branches,
    upsert_commits,
    upsert_issues,
    upsert_prs,
    upsert_releases,
)
from storage.db import get_session, init_db
from storage.metrics import add_metric

import logging
from storage.logging_config import configure_logging

logger = logging.getLogger("refresh_cache")
status_logger = logging.getLogger("refresh.status")

try:
    from data_viewer.data_viewer.distinguished_owners import DISTINGUISHED_OWNERS
except ImportError:
    DISTINGUISHED_OWNERS = []


ENTITY_TYPES = ["branches", "commits", "issues", "prs", "releases"]
COMMIT_COLUMNS = [
    "oid",
    "authoredDate",
    "messageHeadline",
    "additions",
    "deletions",
    "author_name",
    "author_login",
]


def _format_duration(seconds: float) -> str:
    total_seconds = int(round(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def fetch_repos_for_owner(owner: str, token: str) -> list[str]:
    headers = {"Authorization": f"token {token}"}
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{owner}/repos?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            logger.warning("Failed to list repos for %s (status=%s)", owner, resp.status_code)
            break
        data = resp.json()
        if not data:
            break
        repos.extend([repo["name"] for repo in data])
        if len(data) < 100:
            break
        page += 1
    return repos


def commits_to_df(commits):
    rows = []
    for commit in commits:
        rows.append(
            {
                "authoredDate": commit.authored_date,
                "messageHeadline": commit.message,
                "additions": commit.additions,
                "deletions": commit.deletions,
                "author_login": commit.author_login,
            }
        )
    return pd.DataFrame(rows)


def issues_to_df(issues):
    rows = []
    for issue in issues:
        rows.append(
            {
                "id": issue.github_id,
                "createdAt": issue.created_at,
                "closedAt": issue.closed_at,
                "state": issue.state,
                "author_login": issue.author_login,
                "first_comment_createdAt": issue.first_comment_created_at,
                "first_comment_author": issue.first_comment_author,
                "labels": issue.labels or [],
            }
        )
    df = pd.DataFrame(rows)
    return df.reindex(
        columns=[
            "id",
            "createdAt",
            "closedAt",
            "state",
            "author_login",
            "first_comment_createdAt",
            "first_comment_author",
            "labels",
        ]
    )


def prs_to_df(prs):
    rows = []
    for pr in prs:
        rows.append(
            {
                "id": pr.github_id,
                "createdAt": pr.created_at,
                "mergedAt": pr.merged_at,
                "closedAt": pr.closed_at,
                "state": pr.state,
                "author_login": pr.author_login,
                "first_comment_createdAt": pr.first_comment_created_at,
                "first_comment_author": pr.first_comment_author,
                "labels": pr.labels or [],
            }
        )
    df = pd.DataFrame(rows)
    return df.reindex(
        columns=[
            "id",
            "createdAt",
            "mergedAt",
            "closedAt",
            "state",
            "author_login",
            "first_comment_createdAt",
            "first_comment_author",
            "labels",
        ]
    )


def releases_to_df(releases):
    rows = []
    for release in releases:
        rows.append(
            {
                "name": release.name,
                "tag_name": release.tag_name,
                "created_at": release.created_at,
                "total_downloads": release.total_downloads,
            }
        )
    df = pd.DataFrame(rows)
    return df.reindex(columns=["name", "tag_name", "created_at", "total_downloads"])


def branches_to_df(branches):
    rows = []
    for branch in branches:
        rows.append(
            {
                "branch_name": branch.name,
                "total_commits": branch.total_commits,
                "last_commit_date": branch.last_commit_date,
            }
        )
    df = pd.DataFrame(rows)
    return df.reindex(columns=["branch_name", "total_commits", "last_commit_date"])


def normalize_datetime_columns(df, columns):
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def empty_commits_df() -> pd.DataFrame:
    return pd.DataFrame(columns=COMMIT_COLUMNS)


def _coerce_timestamp(value):
    if value is None:
        return None
    ts = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def _coerce_int(value) -> int:
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
    except Exception:
        pass
    return int(value)


def _timestamps_equal(left, right) -> bool:
    left_ts = _coerce_timestamp(left)
    right_ts = _coerce_timestamp(right)
    if left_ts is None or right_ts is None:
        return left_ts is None and right_ts is None
    return left_ts == right_ts


def _branch_snapshot(branches_df: pd.DataFrame, branch_name: str | None):
    if branches_df is None or branches_df.empty or not branch_name:
        return None
    matches = branches_df[branches_df["branch_name"] == branch_name]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return {
        "name": branch_name,
        "total_commits": _coerce_int(row.get("total_commits")),
        "last_commit_date": _coerce_timestamp(row.get("last_commit_date")),
        "head_oid": row.get("head_oid"),
    }


def _load_cached_commits_df(session, repo_id: int) -> pd.DataFrame:
    return normalize_datetime_columns(
        commits_to_df(get_cached_commits(session, repo_id)),
        ["authoredDate"],
    )


def _fetch_full_commits(owner: str, repo: str, branch: str | None, token: str) -> pd.DataFrame:
    if not branch:
        return empty_commits_df()
    commits_df = process_commits({"owner": owner, "repo": repo, "branch": branch}, token)
    if commits_df is None:
        return empty_commits_df()
    return normalize_datetime_columns(commits_df, ["authoredDate"])


def _fetch_incremental_commits(
    session,
    *,
    repo_id: int,
    owner: str,
    repo: str,
    branch: str,
    token: str,
    expected_new: int,
) -> bool:
    collected_new = 0
    after_cursor = None
    has_next_page = True

    while has_next_page and collected_new < expected_new:
        commit_rows, page_info = fetch_commit_page(
            {"owner": owner, "repo": repo, "branch": branch},
            token,
            after_cursor=after_cursor,
            first=100,
        )
        if not commit_rows:
            break

        existing_oids = get_existing_commit_oids(
            session,
            repo_id,
            [row["oid"] for row in commit_rows],
        )
        unseen_rows = [row for row in commit_rows if row["oid"] not in existing_oids]
        if unseen_rows:
            upsert_commits(
                session,
                repo_id,
                unseen_rows,
                owner=owner,
                repo=repo,
            )
            collected_new += len(unseen_rows)

        after_cursor = page_info["endCursor"]
        has_next_page = page_info["hasNextPage"]

    return collected_new >= expected_new


def _sync_commits(
    session,
    *,
    repo_id: int,
    owner: str,
    repo: str,
    branch_name: str | None,
    token: str,
    branches_df: pd.DataFrame,
    cached_default_branch: str | None,
) -> pd.DataFrame:
    if not branch_name:
        logger.info("Skipping commits for %s/%s: no default branch", owner, repo)
        delete_cached_commits(session, repo_id)
        return empty_commits_df()

    fresh_branch = _branch_snapshot(branches_df, branch_name)
    if fresh_branch is None:
        logger.info("Skipping commits for %s/%s: default branch %s not found in branch list", owner, repo, branch_name)
        delete_cached_commits(session, repo_id)
        return empty_commits_df()

    cached_commit_count = get_cached_commit_count(session, repo_id)
    cached_branch = get_cached_branch(session, repo_id, cached_default_branch or branch_name)
    default_branch_changed = bool(cached_default_branch and cached_default_branch != branch_name)
    head_oid_exists = bool(
        fresh_branch["head_oid"]
        and get_existing_commit_oids(session, repo_id, [fresh_branch["head_oid"]])
    )

    mode = "rebuild"
    reason = "initial_sync"
    expected_new = 0

    if default_branch_changed:
        reason = "default_branch_changed"
    elif cached_commit_count == 0 or cached_branch is None:
        reason = "missing_cached_commits"
    else:
        cached_total = _coerce_int(cached_branch.total_commits)
        fresh_total = fresh_branch["total_commits"]
        if fresh_total < cached_total:
            reason = "commit_count_decreased"
        elif fresh_total == cached_total:
            if _timestamps_equal(fresh_branch["last_commit_date"], cached_branch.last_commit_date) and head_oid_exists:
                mode = "skip"
                reason = "branch_head_unchanged"
            else:
                reason = "branch_head_mismatch"
        else:
            expected_new = fresh_total - cached_total
            if head_oid_exists:
                reason = "head_oid_already_cached_with_count_increase"
            else:
                mode = "incremental"
                reason = f"count_increased_by_{expected_new}"

    logger.info(
        "Commit sync for %s/%s: mode=%s reason=%s expected_new=%s",
        owner,
        repo,
        mode,
        reason,
        expected_new,
    )
    status_logger.info(
        "owner=%s repo=%s stage=commit_sync status=ready mode=%s reason=%s expected_new=%s",
        owner,
        repo,
        mode,
        reason,
        expected_new,
    )

    if mode == "skip":
        return _load_cached_commits_df(session, repo_id)

    if mode == "incremental":
        if _fetch_incremental_commits(
            session,
            repo_id=repo_id,
            owner=owner,
            repo=repo,
            branch=branch_name,
            token=token,
            expected_new=expected_new,
        ):
            return _load_cached_commits_df(session, repo_id)

        logger.warning(
            "Incremental commit sync could not reconcile %s/%s; rebuilding full default branch history",
            owner,
            repo,
        )

    commits_df_full = _fetch_full_commits(owner, repo, branch_name, token)
    if fresh_branch["total_commits"] > 0 and commits_df_full.empty:
        raise RuntimeError(
            f"Full commit fetch returned no commits for {owner}/{repo} on branch {branch_name}"
        )
    if commits_df_full.empty:
        delete_cached_commits(session, repo_id)
        return commits_df_full
    delete_cached_commits(session, repo_id, commit=False)
    upsert_commits(
        session,
        repo_id,
        commits_df_full.to_dict("records"),
        owner=owner,
        repo=repo,
    )
    return commits_df_full


def _count_recent(df: pd.DataFrame, column: str, since: pd.Timestamp) -> int:
    if df is None or df.empty or column not in df.columns:
        return 0
    values = pd.to_datetime(df[column], utc=True, errors="coerce")
    return int(values.ge(since).sum())


def _latest_timestamp(df: pd.DataFrame, column: str):
    if df is None or df.empty or column not in df.columns:
        return None
    values = pd.to_datetime(df[column], utc=True, errors="coerce")
    if values.dropna().empty:
        return None
    return values.max()


def _compute_activity_score(
    *,
    commits_90d: int,
    prs_opened_90d: int,
    prs_merged_90d: int,
    issues_opened_90d: int,
    issues_closed_90d: int,
    releases_90d: int,
    last_commit_at,
    now: pd.Timestamp,
) -> float:
    score = (
        commits_90d * 0.25
        + prs_merged_90d * 5.0
        + prs_opened_90d * 2.0
        + issues_closed_90d * 2.0
        + issues_opened_90d * 0.5
        + releases_90d * 3.0
    )

    if last_commit_at is not None:
        days_since_last_commit = (now - last_commit_at).days
        if days_since_last_commit <= 30:
            score += 10
        elif days_since_last_commit <= 90:
            score += 5

    return float(score)


def compute_activity_metrics(
    session,
    run_id,
    commits_df: pd.DataFrame,
    issues_df: pd.DataFrame,
    prs_df: pd.DataFrame,
    releases_df: pd.DataFrame,
    window_days: int = 90,
):
    now = pd.Timestamp.now(tz="UTC")
    since = now - pd.Timedelta(days=window_days)

    commits_90d = _count_recent(commits_df, "authoredDate", since)
    prs_opened_90d = _count_recent(prs_df, "createdAt", since)
    prs_merged_90d = _count_recent(prs_df, "mergedAt", since)
    issues_opened_90d = _count_recent(issues_df, "createdAt", since)
    issues_closed_90d = _count_recent(issues_df, "closedAt", since)
    releases_90d = _count_recent(releases_df, "created_at", since)
    last_commit_at = _latest_timestamp(commits_df, "authoredDate")
    score_90d = _compute_activity_score(
        commits_90d=commits_90d,
        prs_opened_90d=prs_opened_90d,
        prs_merged_90d=prs_merged_90d,
        issues_opened_90d=issues_opened_90d,
        issues_closed_90d=issues_closed_90d,
        releases_90d=releases_90d,
        last_commit_at=last_commit_at,
        now=now,
    )

    add_metric(session, run_id=run_id, scope="activity", name="score_90d", value=score_90d)
    add_metric(session, run_id=run_id, scope="activity", name="commits_90d", value=commits_90d)
    add_metric(session, run_id=run_id, scope="activity", name="prs_opened_90d", value=prs_opened_90d)
    add_metric(session, run_id=run_id, scope="activity", name="prs_merged_90d", value=prs_merged_90d)
    add_metric(session, run_id=run_id, scope="activity", name="issues_opened_90d", value=issues_opened_90d)
    add_metric(session, run_id=run_id, scope="activity", name="issues_closed_90d", value=issues_closed_90d)
    add_metric(session, run_id=run_id, scope="activity", name="releases_90d", value=releases_90d)
    if last_commit_at is not None:
        add_metric(
            session,
            run_id=run_id,
            scope="activity",
            name="last_commit_at",
            value=last_commit_at.isoformat(),
        )


def compute_commit_metrics(session, run_id, commit_analyzer, contribution_type="commits"):
    total_commits = len(commit_analyzer.df_commits)
    total_contributors = commit_analyzer.df_commits["author_login"].nunique()
    bus_factor = commit_analyzer.bus_factor(contribution_type)
    hhi = commit_analyzer.contributor_diversity_hhi(contribution_type)
    new_contributors, active_core = commit_analyzer.new_vs_core_contributors(
        90, contribution_type
    )
    days_since_last, last_commit_date = commit_analyzer.staleness()

    add_metric(session, run_id=run_id, scope="commits", name="total_commits", value=total_commits)
    add_metric(session, run_id=run_id, scope="commits", name="total_contributors", value=total_contributors)
    add_metric(session, run_id=run_id, scope="commits", name="bus_factor", value=bus_factor)
    add_metric(session, run_id=run_id, scope="commits", name="hhi", value=float(hhi))
    add_metric(session, run_id=run_id, scope="commits", name="new_contributors", value=new_contributors)
    add_metric(session, run_id=run_id, scope="commits", name="active_core_contributors", value=active_core)
    if days_since_last is not None:
        add_metric(session, run_id=run_id, scope="commits", name="staleness_days", value=days_since_last)
    if last_commit_date is not None:
        add_metric(
            session,
            run_id=run_id,
            scope="commits",
            name="last_commit_date",
            value=last_commit_date.isoformat(),
        )


def compute_issue_pr_metrics(session, run_id, issue_analyzer: IssuePRAnalyzer):
    has_issues = issue_analyzer.df_issues is not None and not issue_analyzer.df_issues.empty
    has_prs = issue_analyzer.df_prs is not None and not issue_analyzer.df_prs.empty

    # Issues
    if has_issues:
        add_metric(
            session,
            run_id=run_id,
            scope="issues",
            name="median_time_to_first_response_hours",
            value=issue_analyzer.time_to_first_response("issue").total_seconds() / 3600,
        )
        add_metric(
            session,
            run_id=run_id,
            scope="issues",
            name="issue_closure_ratio_90d",
            value=issue_analyzer.issue_closure_ratio(90),
        )
        add_metric(
            session,
            run_id=run_id,
            scope="issues",
            name="median_time_to_close_days",
            value=issue_analyzer.time_to_close("issue").total_seconds() / 86400,
        )
        add_metric(
            session,
            run_id=run_id,
            scope="issues",
            name="backlog_size",
            value=issue_analyzer.backlog_size(),
        )
        add_metric(
            session,
            run_id=run_id,
            scope="issues",
            name="good_first_issue_velocity_90d",
            value=issue_analyzer.good_first_issue_velocity(90),
        )
    else:
        add_metric(session, run_id=run_id, scope="issues", name="median_time_to_first_response_hours", value=0.0)
        add_metric(session, run_id=run_id, scope="issues", name="issue_closure_ratio_90d", value=0.0)
        add_metric(session, run_id=run_id, scope="issues", name="median_time_to_close_days", value=0.0)
        add_metric(session, run_id=run_id, scope="issues", name="backlog_size", value=0)
        add_metric(session, run_id=run_id, scope="issues", name="good_first_issue_velocity_90d", value=0)

    # PRs
    if has_prs:
        add_metric(
            session,
            run_id=run_id,
            scope="prs",
            name="median_time_to_first_response_hours",
            value=issue_analyzer.time_to_first_response("pr").total_seconds() / 3600,
        )
        add_metric(
            session,
            run_id=run_id,
            scope="prs",
            name="median_time_to_close_days",
            value=issue_analyzer.time_to_close("pr").total_seconds() / 86400,
        )
        add_metric(
            session,
            run_id=run_id,
            scope="prs",
            name="median_pr_merge_time_days",
            value=issue_analyzer.pr_merge_time().total_seconds() / 86400,
        )
    else:
        add_metric(session, run_id=run_id, scope="prs", name="median_time_to_first_response_hours", value=0.0)
        add_metric(session, run_id=run_id, scope="prs", name="median_time_to_close_days", value=0.0)
        add_metric(session, run_id=run_id, scope="prs", name="median_pr_merge_time_days", value=0.0)


def compute_release_metrics(session, run_id, release_analyzer: ReleaseAnalyzer):
    add_metric(
        session,
        run_id=run_id,
        scope="releases",
        name="total_downloads",
        value=release_analyzer.total_downloads(),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="releases",
        name="release_count",
        value=len(release_analyzer.df_releases),
    )


def compute_repo_metrics(session, run_id, repo_info: dict) -> None:
    if not repo_info:
        return

    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="default_branch",
        value=repo_info.get("defaultBranchRef", {}).get("name"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="stars",
        value=repo_info.get("stargazerCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="forks",
        value=repo_info.get("forkCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="watchers",
        value=repo_info.get("watchers", {}).get("totalCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="open_issues",
        value=repo_info.get("issues", {}).get("totalCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="closed_issues",
        value=repo_info.get("closedIssues", {}).get("totalCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="open_prs",
        value=repo_info.get("pullRequests", {}).get("totalCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="closed_prs",
        value=repo_info.get("closedPullRequests", {}).get("totalCount"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="created_at",
        value=repo_info.get("createdAt"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="updated_at",
        value=repo_info.get("updatedAt"),
    )
    add_metric(
        session,
        run_id=run_id,
        scope="repo",
        name="is_archived",
        value=repo_info.get("isArchived"),
    )


def compute_governance_metrics(session, run_id, governance_flags: dict) -> None:
    for name, value in governance_flags.items():
        add_metric(session, run_id=run_id, scope="governance", name=name, value=int(value))


def collect_for_repo(
    session,
    owner,
    repo,
    token,
    force_refresh,
):
    status_logger.info("owner=%s repo=%s stage=start status=begin", owner, repo)
    logger.info("Collecting %s/%s", owner, repo)
    repo_obj = get_or_create_repo(session, owner, repo, None)
    cached_default_branch = repo_obj.default_branch
    default_branch = repo_obj.default_branch

    cache_fresh = {
        entity: is_cache_fresh(session, repo_obj.id, entity) for entity in ENTITY_TYPES
    }
    needs_refresh = force_refresh or not all(cache_fresh.values())

    status_logger.info(
        "owner=%s repo=%s stage=cache_decision status=ready needs_refresh=%s",
        owner,
        repo,
        needs_refresh,
    )

    logger.info(
        "Cache decision for %s/%s: needs_refresh=%s (force_refresh=%s, fresh=%s)",
        owner,
        repo,
        needs_refresh,
        force_refresh,
        cache_fresh,
    )

    repo_info = {}
    if needs_refresh:
        logger.info("Fetching fresh data for %s/%s", owner, repo)
        status_logger.info("owner=%s repo=%s stage=repo_info status=start", owner, repo)
        repo_info_start = time.monotonic()
        info_result = github_api_call(
            repo_info_query,
            {"owner": owner, "repo": repo},
            token,
            request_name="repo_info",
        )
        repo_info = info_result.get("data", {}).get("repository", {})
        status_logger.info(
            "owner=%s repo=%s stage=repo_info status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - repo_info_start),
        )
        fetched_default_branch = repo_info.get("defaultBranchRef", {}).get("name")
        if fetched_default_branch:
            default_branch = fetched_default_branch
            if repo_obj.default_branch != default_branch:
                repo_obj.default_branch = default_branch
                session.add(repo_obj)
                session.commit()

        status_logger.info("owner=%s repo=%s stage=branches status=start", owner, repo)
        branches_start = time.monotonic()
        branches_df = process_branches({"owner": owner, "repo": repo}, token)
        status_logger.info(
            "owner=%s repo=%s stage=branches status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - branches_start),
        )
        branches_df = normalize_datetime_columns(branches_df, ["last_commit_date"])

        status_logger.info("owner=%s repo=%s stage=commits status=start", owner, repo)
        commits_start = time.monotonic()
        commits_df_full = _sync_commits(
            session,
            repo_id=repo_obj.id,
            owner=owner,
            repo=repo,
            branch_name=default_branch,
            token=token,
            branches_df=branches_df,
            cached_default_branch=cached_default_branch,
        )
        status_logger.info(
            "owner=%s repo=%s stage=commits status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - commits_start),
        )
        status_logger.info("owner=%s repo=%s stage=issues status=start", owner, repo)
        issues_start = time.monotonic()
        issues_df = process_issues({"owner": owner, "repo": repo}, token)
        status_logger.info(
            "owner=%s repo=%s stage=issues status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - issues_start),
        )
        status_logger.info("owner=%s repo=%s stage=prs status=start", owner, repo)
        prs_start = time.monotonic()
        prs_df = process_prs({"owner": owner, "repo": repo}, token)
        status_logger.info(
            "owner=%s repo=%s stage=prs status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - prs_start),
        )
        status_logger.info("owner=%s repo=%s stage=releases status=start", owner, repo)
        releases_start = time.monotonic()
        releases_df = process_releases({"owner": owner, "repo": repo}, token)
        status_logger.info(
            "owner=%s repo=%s stage=releases status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - releases_start),
        )

        issues_df = normalize_datetime_columns(issues_df, ["createdAt", "closedAt", "first_comment_createdAt"])
        prs_df = normalize_datetime_columns(prs_df, ["createdAt", "mergedAt", "closedAt", "first_comment_createdAt"])
        releases_df = normalize_datetime_columns(releases_df, ["created_at"])

        upsert_branches(
            session,
            repo_obj.id,
            branches_df.to_dict("records"),
            owner=owner,
            repo=repo,
        )
        upsert_issues(
            session,
            repo_obj.id,
            issues_df.to_dict("records"),
            owner=owner,
            repo=repo,
        )
        upsert_prs(
            session,
            repo_obj.id,
            prs_df.to_dict("records"),
            owner=owner,
            repo=repo,
        )
        upsert_releases(
            session,
            repo_obj.id,
            releases_df.to_dict("records"),
            owner=owner,
            repo=repo,
        )

        for entity in ENTITY_TYPES:
            record_fetch(session, repo_obj.id, entity)
    else:
        logger.info("Reusing cached data for %s/%s", owner, repo)
        reuse_start = time.monotonic()
        branches_df = normalize_datetime_columns(branches_to_df(get_cached_branches(session, repo_obj.id)), ["last_commit_date"])
        commits_df_full = normalize_datetime_columns(commits_to_df(get_cached_commits(session, repo_obj.id)), ["authoredDate"])
        issues_df = normalize_datetime_columns(issues_to_df(get_cached_issues(session, repo_obj.id)), ["createdAt", "closedAt", "first_comment_createdAt"])
        prs_df = normalize_datetime_columns(prs_to_df(get_cached_prs(session, repo_obj.id)), ["createdAt", "mergedAt", "closedAt", "first_comment_createdAt"])
        releases_df = normalize_datetime_columns(releases_to_df(get_cached_releases(session, repo_obj.id)), ["created_at"])
        status_logger.info(
            "owner=%s repo=%s stage=reuse_cache status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - reuse_start),
        )

    commits_df_recent = commits_df_full
    issues_df_recent = issues_df
    prs_df_recent = prs_df
    releases_df_recent = releases_df

    run = create_run(
        session=session,
        repo_id=repo_obj.id,
        source="scheduled",
        notes="cache refresh" if needs_refresh else "cache reuse",
    )

    if needs_refresh:
        status_logger.info("owner=%s repo=%s stage=repo_metrics status=start", owner, repo)
        repo_metrics_start = time.monotonic()
        compute_repo_metrics(session, run.id, repo_info)
        status_logger.info(
            "owner=%s repo=%s stage=repo_metrics status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - repo_metrics_start),
        )

        status_logger.info("owner=%s repo=%s stage=governance status=start", owner, repo)
        governance_start = time.monotonic()
        try:
            governance_flags = fetch_governance_files({"owner": owner, "repo": repo}, token)
            compute_governance_metrics(session, run.id, governance_flags)
        except Exception:
            logger.warning("Failed to fetch governance files for %s/%s", owner, repo, exc_info=True)
        status_logger.info(
            "owner=%s repo=%s stage=governance status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - governance_start),
        )

    if not commits_df_recent.empty:
        status_logger.info("owner=%s repo=%s stage=commit_metrics status=start", owner, repo)
        commit_metrics_start = time.monotonic()
        commit_analyzer = CommitAnalyzer(
            commits_df_recent,
            df_commits_full=commits_df_full,
        )
        compute_commit_metrics(session, run.id, commit_analyzer)
        status_logger.info(
            "owner=%s repo=%s stage=commit_metrics status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - commit_metrics_start),
        )

    if not issues_df_recent.empty or not prs_df_recent.empty:
        status_logger.info("owner=%s repo=%s stage=issue_pr_metrics status=start", owner, repo)
        issue_pr_metrics_start = time.monotonic()
        issue_analyzer = IssuePRAnalyzer(issues_df_recent, prs_df_recent)
        compute_issue_pr_metrics(session, run.id, issue_analyzer)
        status_logger.info(
            "owner=%s repo=%s stage=issue_pr_metrics status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - issue_pr_metrics_start),
        )

    if not releases_df_recent.empty:
        status_logger.info("owner=%s repo=%s stage=release_metrics status=start", owner, repo)
        release_metrics_start = time.monotonic()
        release_analyzer = ReleaseAnalyzer(releases_df_recent)
        compute_release_metrics(session, run.id, release_analyzer)
        status_logger.info(
            "owner=%s repo=%s stage=release_metrics status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - release_metrics_start),
        )

    status_logger.info("owner=%s repo=%s stage=activity_metrics status=start", owner, repo)
    activity_metrics_start = time.monotonic()
    compute_activity_metrics(
        session,
        run.id,
        commits_df_full,
        issues_df_recent,
        prs_df_recent,
        releases_df_recent,
    )
    status_logger.info(
        "owner=%s repo=%s stage=activity_metrics status=ok duration=%s",
        owner,
        repo,
        _format_duration(time.monotonic() - activity_metrics_start),
    )

    status_logger.info("owner=%s repo=%s stage=done status=ok", owner, repo)


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh maturity data cache.")
    parser.add_argument("--owner", help="GitHub owner/org to refresh")
    parser.add_argument("--repo", help="Specific repo name to refresh")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh even if cache is fresh",
    )
    return parser.parse_args()


def main():
    configure_logging()
    load_dotenv(os.path.join(repo_root, ".env"))
    args = parse_args()
    from storage.secrets import get_secret

    token = get_secret("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    init_db()
    session = get_session()

    owners = [args.owner] if args.owner else list(DISTINGUISHED_OWNERS)
    if not owners:
        raise SystemExit("No owners provided and DISTINGUISHED_OWNERS is empty")

    for owner in owners:
        repos = [args.repo] if args.repo else fetch_repos_for_owner(owner, token)
        status_logger.info("owner=%s repo=* stage=owner_start status=begin", owner)
        for repo in repos:
            logger.info("Processing %s/%s (force_refresh=%s)", owner, repo, args.force_refresh)
            collect_for_repo(
                session=session,
                owner=owner,
                repo=repo,
                token=token,
                force_refresh=args.force_refresh,
            )
        status_logger.info("owner=%s repo=* stage=owner_done status=ok", owner)


if __name__ == "__main__":
    main()
