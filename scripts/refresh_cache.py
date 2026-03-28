import argparse
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

from maturity_tools.analyzers import CommitAnalyzer, IssuePRAnalyzer, ReleaseAnalyzer
from maturity_tools.github_call import (
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
    get_cached_branches,
    get_cached_commits,
    get_cached_issues,
    get_cached_prs,
    get_cached_releases,
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

        variables = {"owner": owner, "repo": repo, "branch": default_branch}
        status_logger.info("owner=%s repo=%s stage=branches status=start", owner, repo)
        branches_start = time.monotonic()
        branches_df = process_branches({"owner": owner, "repo": repo}, token)
        status_logger.info(
            "owner=%s repo=%s stage=branches status=ok duration=%s",
            owner,
            repo,
            _format_duration(time.monotonic() - branches_start),
        )
        status_logger.info("owner=%s repo=%s stage=commits status=start", owner, repo)
        commits_start = time.monotonic()
        commits_df_full = process_commits(variables, token)
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

        branches_df = normalize_datetime_columns(branches_df, ["last_commit_date"])
        commits_df_full = normalize_datetime_columns(commits_df_full, ["authoredDate"])
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
        upsert_commits(
            session,
            repo_obj.id,
            commits_df_full.to_dict("records"),
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
