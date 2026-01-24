import argparse
from datetime import datetime, timedelta, timezone
import os

import pandas as pd
import requests
from dotenv import load_dotenv

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

try:
    from data_viewer.data_viewer.distinguished_owners import DISTINGUISHED_OWNERS
except ImportError:
    DISTINGUISHED_OWNERS = []


ENTITY_TYPES = ["branches", "commits", "issues", "prs", "releases"]


def fetch_repos_for_owner(owner: str, token: str) -> list[str]:
    headers = {"Authorization": f"token {token}"}
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{owner}/repos?per_page=100&page={page}"
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        repos.extend([repo["name"] for repo in data])
        if len(data) < 100:
            break
        page += 1
    return repos


def calculate_since_date(time_range: str | None):
    if not time_range or time_range.lower() == "all":
        return None
    now = datetime.now(timezone.utc)
    if time_range == "6 months":
        return now - timedelta(days=180)
    if time_range == "1 year":
        return now - timedelta(days=365)
    if time_range == "2 years":
        return now - timedelta(days=730)
    if time_range == "3 years":
        return now - timedelta(days=1095)
    return None


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
    return pd.DataFrame(rows)


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
    return pd.DataFrame(rows)


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
    return pd.DataFrame(rows)


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
    return pd.DataFrame(rows)


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


def collect_for_repo(
    session,
    owner,
    repo,
    token,
    time_range,
    since_date,
    full_history,
    force_refresh,
):
    info_result = github_api_call(
        repo_info_query,
        {"owner": owner, "repo": repo},
        token,
    )
    default_branch = (
        info_result.get("data", {})
        .get("repository", {})
        .get("defaultBranchRef", {})
        .get("name")
    )
    repo_obj = get_or_create_repo(session, owner, repo, default_branch)

    cache_fresh = {
        entity: is_cache_fresh(session, repo_obj.id, entity) for entity in ENTITY_TYPES
    }
    needs_refresh = force_refresh or not all(cache_fresh.values())

    variables = {"owner": owner, "repo": repo, "branch": default_branch}
    since_variables = variables.copy()
    if since_date:
        since_variables["since"] = since_date.isoformat()

    if needs_refresh:
        branches_df = process_branches({"owner": owner, "repo": repo}, token)
        commits_df_full = process_commits(variables, token)
        issues_df = process_issues(
            since_variables if not full_history else {"owner": owner, "repo": repo},
            token,
        )
        prs_df = process_prs(
            since_variables if not full_history else {"owner": owner, "repo": repo},
            token,
        )
        releases_df = process_releases(
            since_variables if not full_history else {"owner": owner, "repo": repo},
            token,
        )

        upsert_branches(session, repo_obj.id, branches_df.to_dict("records"))
        upsert_commits(session, repo_obj.id, commits_df_full.to_dict("records"))
        upsert_issues(session, repo_obj.id, issues_df.to_dict("records"))
        upsert_prs(session, repo_obj.id, prs_df.to_dict("records"))
        upsert_releases(session, repo_obj.id, releases_df.to_dict("records"))

        for entity in ENTITY_TYPES:
            record_fetch(session, repo_obj.id, entity)
    else:
        branches_df = branches_to_df(get_cached_branches(session, repo_obj.id))
        commits_df_full = commits_to_df(get_cached_commits(session, repo_obj.id))
        issues_df = issues_to_df(get_cached_issues(session, repo_obj.id))
        prs_df = prs_to_df(get_cached_prs(session, repo_obj.id))
        releases_df = releases_to_df(get_cached_releases(session, repo_obj.id))

    if since_date:
        commits_df_recent = commits_df_full[commits_df_full["authoredDate"] >= since_date]
        issues_df_recent = issues_df[issues_df["createdAt"] >= since_date]
        prs_df_recent = prs_df[prs_df["createdAt"] >= since_date]
        releases_df_recent = releases_df[releases_df["created_at"] >= since_date]
    else:
        commits_df_recent = commits_df_full
        issues_df_recent = issues_df
        prs_df_recent = prs_df
        releases_df_recent = releases_df

    run = create_run(
        session=session,
        repo_id=repo_obj.id,
        time_range=time_range,
        since_date=since_date,
        source="scheduled",
        notes="cache refresh" if needs_refresh else "cache reuse",
    )

    if not commits_df_recent.empty:
        commit_analyzer = CommitAnalyzer(
            commits_df_recent,
            df_commits_full=commits_df_full,
        )
        compute_commit_metrics(session, run.id, commit_analyzer)

    if not issues_df_recent.empty or not prs_df_recent.empty:
        issue_analyzer = IssuePRAnalyzer(issues_df_recent, prs_df_recent)
        compute_issue_pr_metrics(session, run.id, issue_analyzer)

    if not releases_df_recent.empty:
        release_analyzer = ReleaseAnalyzer(releases_df_recent)
        compute_release_metrics(session, run.id, release_analyzer)


def parse_args():
    parser = argparse.ArgumentParser(description="Refresh maturity data cache.")
    parser.add_argument("--owner", help="GitHub owner/org to refresh")
    parser.add_argument("--repo", help="Specific repo name to refresh")
    parser.add_argument(
        "--time-range",
        default="6 months",
        choices=["6 months", "1 year", "2 years", "3 years", "all"],
        help="Time range for metrics computation",
    )
    parser.add_argument(
        "--no-full-history",
        action="store_false",
        dest="full_history",
        help="Limit raw entity fetches to the selected time range",
    )
    parser.set_defaults(full_history=True)
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Refresh even if cache is fresh",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    init_db()
    session = get_session()

    owners = [args.owner] if args.owner else list(DISTINGUISHED_OWNERS)
    if not owners:
        raise SystemExit("No owners provided and DISTINGUISHED_OWNERS is empty")

    since_date = calculate_since_date(args.time_range)

    for owner in owners:
        repos = [args.repo] if args.repo else fetch_repos_for_owner(owner, token)
        for repo in repos:
            collect_for_repo(
                session=session,
                owner=owner,
                repo=repo,
                token=token,
                time_range=args.time_range,
                since_date=since_date,
                full_history=args.full_history,
                force_refresh=args.force_refresh,
            )


if __name__ == "__main__":
    main()
