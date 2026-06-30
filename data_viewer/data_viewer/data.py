from maturity_tools.github_call import process_commits, process_branches, process_releases, process_issues, process_prs
import pandas as pd
import streamlit as st

from storage.cache import (
    get_cached_branches,
    get_cached_commits,
    get_cached_issues,
    get_cached_prs,
    get_cached_releases,
    # NOTE: DB-cache mode in the viewer is intentionally read-only.
    # Cache refresh is handled by scheduled scripts; the viewer only fetches
    # from GitHub when no cache entry exists yet (handled in main.py).
)
from storage.models import Metric, Repo, RepoScanJob, Run, Summary
from sqlalchemy import select

# Cache branch results until owner/repo changes
@st.cache_data(show_spinner=True)
def get_branches_cached(owner, repo, token):
    # Branches don't have timestamps, so we cache only by owner/repo
    variables = {"owner": owner, "repo": repo}
    return process_branches(variables, token)

@st.cache_data(show_spinner=True)
def get_commits_cached(owner, repo, branch, token):
    variables = {"owner": owner, "repo": repo, "branch": branch}
    return process_commits(variables, token)

@st.cache_data(show_spinner=True)
def get_releases_cached(owner, repo, token):
    variables = {"owner": owner, "repo": repo}
    return process_releases(variables, token)

@st.cache_data(show_spinner=True)
def get_issues_cached(owner, repo, token):
    variables = {"owner": owner, "repo": repo}
    return process_issues(variables, token)

@st.cache_data(show_spinner=True)
def get_prs_cached(owner, repo, token):
    variables = {"owner": owner, "repo": repo}
    return process_prs(variables, token)


def _branches_to_df(branches):
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
    return _normalize_branches_df(df)


def _normalize_branches_df(df):
    if "last_commit_date" in df.columns:
        df["last_commit_date"] = pd.to_datetime(df["last_commit_date"], utc=True, errors="coerce")
    return df.reindex(columns=["branch_name", "total_commits", "last_commit_date"])


def _commits_to_df(commits):
    rows = []
    for commit in commits:
        rows.append(
            {
                "oid": commit.oid,
                "authoredDate": commit.authored_date,
                "messageHeadline": commit.message,
                "additions": commit.additions,
                "deletions": commit.deletions,
                "author_login": commit.author_login,
            }
        )
    df = pd.DataFrame(rows)
    return _normalize_commits_df(df)


def _normalize_commits_df(df):
    if "authoredDate" in df.columns:
        df["authoredDate"] = pd.to_datetime(df["authoredDate"], utc=True, errors="coerce")
    return df.reindex(
        columns=[
            "oid",
            "authoredDate",
            "messageHeadline",
            "additions",
            "deletions",
            "author_login",
        ]
    )


def _issues_to_df(issues):
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
    return _normalize_issues_df(df)


def _normalize_issues_df(df):
    for col in ["createdAt", "closedAt", "first_comment_createdAt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
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


def _prs_to_df(prs):
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
    return _normalize_prs_df(df)


def _normalize_prs_df(df):
    for col in ["createdAt", "mergedAt", "closedAt", "first_comment_createdAt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
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


def _releases_to_df(releases):
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
    return _normalize_releases_df(df)


def _normalize_releases_df(df):
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    return df.reindex(columns=["name", "tag_name", "created_at", "total_downloads"])


def get_branches_data(
    owner,
    repo,
    token,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    if not use_db_cache or session is None or repo_id is None:
        branches_df = get_branches_cached(owner, repo, token)
        return _normalize_branches_df(branches_df)

    with st.spinner("Loading branches..."):
        return _branches_to_df(get_cached_branches(session, repo_id))


def get_commits_data(
    owner,
    repo,
    branch,
    token,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    if not use_db_cache or session is None or repo_id is None:
        commits_full_df = _normalize_commits_df(get_commits_cached(owner, repo, branch, token))
        return commits_full_df, commits_full_df

    with st.spinner("Loading commits..."):
        commits_full_df = _commits_to_df(get_cached_commits(session, repo_id))
        return commits_full_df, commits_full_df


def get_releases_data(
    owner,
    repo,
    token,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    if not use_db_cache or session is None or repo_id is None:
        releases_df = get_releases_cached(owner, repo, token)
        return _normalize_releases_df(releases_df)

    with st.spinner("Loading releases..."):
        return _releases_to_df(get_cached_releases(session, repo_id))


def get_issues_data(
    owner,
    repo,
    token,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    if not use_db_cache or session is None or repo_id is None:
        issues_df = get_issues_cached(owner, repo, token)
        return _normalize_issues_df(issues_df)

    with st.spinner("Loading issues..."):
        return _issues_to_df(get_cached_issues(session, repo_id))


def get_prs_data(
    owner,
    repo,
    token,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    if not use_db_cache or session is None or repo_id is None:
        prs_df = get_prs_cached(owner, repo, token)
        return _normalize_prs_df(prs_df)

    with st.spinner("Loading pull requests..."):
        prs_df = _prs_to_df(get_cached_prs(session, repo_id))

    return prs_df


def get_repo_summary_db(session, owner: str, repo: str):
    repo_obj = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == repo)
    ).scalar_one_or_none()
    if not repo_obj:
        return None

    summary = (
        session.execute(
            select(Summary)
            .where(Summary.repo_id == repo_obj.id, Summary.summary_scope == "repo")
            .order_by(Summary.created_at.desc())
        )
        .scalars()
        .first()
    )
    return summary


def get_org_summary_db(session, owner: str):
    summary = (
        session.execute(
            select(Summary)
            .where(Summary.owner == owner, Summary.summary_scope == "org")
            .order_by(Summary.created_at.desc())
        )
        .scalars()
        .first()
    )
    return summary


def _metric_value(metric: Metric):
    if metric.value_int is not None:
        return metric.value_int
    if metric.value_float is not None:
        return metric.value_float
    if metric.value_text is not None:
        return metric.value_text
    return metric.value_json


def get_repo_metrics_db(session, owner: str, repo: str) -> dict | None:
    repo_obj = session.execute(
        select(Repo).where(Repo.owner == owner, Repo.name == repo)
    ).scalar_one_or_none()
    if not repo_obj:
        return None

    latest_run_id = (
        session.execute(
            select(Metric.run_id)
            .join(Run, Run.id == Metric.run_id)
            .where(Run.repo_id == repo_obj.id, Metric.scope == "repo")
            .order_by(Run.run_started_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    )
    if not latest_run_id:
        return None

    metrics = (
        session.execute(
            select(Metric).where(Metric.run_id == latest_run_id, Metric.scope == "repo")
        )
        .scalars()
        .all()
    )
    if not metrics:
        return None

    return {metric.name: _metric_value(metric) for metric in metrics}


def get_owner_repos_by_activity(session, owner: str) -> list[str]:
    activity_score = (
        select(Metric.value_float)
        .join(Run, Run.id == Metric.run_id)
        .where(
            Run.repo_id == Repo.id,
            Metric.scope == "activity",
            Metric.name == "score_90d",
        )
        .order_by(Run.run_started_at.desc())
        .limit(1)
        .scalar_subquery()
    )

    return session.execute(
        select(Repo.name)
        .where(Repo.owner == owner)
        .order_by(activity_score.desc().nulls_last(), Repo.name)
    ).scalars().all()


def get_repo_scan_job(session, scan_id: int) -> RepoScanJob | None:
    return session.get(RepoScanJob, scan_id)
