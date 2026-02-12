from maturity_tools.github_call import process_commits, process_branches, process_releases, process_issues, process_prs
from maturity_tools.github_call import process_commits, process_branches, process_releases, process_issues, process_prs
import pandas as pd
import streamlit as st

from storage.cache import (
    get_cached_branches,
    get_cached_commits,
    get_cached_issues,
    get_cached_prs,
    get_cached_releases,
    is_cache_fresh,
    record_fetch,
    upsert_branches,
    upsert_commits,
    upsert_issues,
    upsert_prs,
    upsert_releases,
)

# Cache branch results until owner/repo changes (ignore since_date for branches)
@st.cache_data(show_spinner=True)
def get_branches_cached(owner, repo, token):
    # Branches don't have timestamps, so we ignore since_date and cache only by owner/repo
    variables = {"owner": owner, "repo": repo}
    return process_branches(variables, token)

@st.cache_data(show_spinner=True)
def get_commits_cached(owner, repo, branch, token, since_date=None):
    variables = {"owner": owner, "repo": repo, "branch": branch}
    if since_date:
        variables["since"] = since_date.isoformat()
    return process_commits(variables, token)

@st.cache_data(show_spinner=True)
def get_releases_cached(owner, repo, token, since_date=None):
    variables = {"owner": owner, "repo": repo}
    if since_date:
        variables["since"] = since_date.isoformat()
    return process_releases(variables, token)

@st.cache_data(show_spinner=True)
def get_issues_cached(owner, repo, token, since_date=None):
    variables = {"owner": owner, "repo": repo}
    if since_date:
        variables["since"] = since_date.isoformat()
    return process_issues(variables, token)

@st.cache_data(show_spinner=True)
def get_prs_cached(owner, repo, token, since_date=None):
    variables = {"owner": owner, "repo": repo}
    if since_date:
        variables["since"] = since_date.isoformat()
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


def _normalize_since_date(since_date):
    if since_date is None:
        return None
    timestamp = pd.to_datetime(since_date, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp


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
        if is_cache_fresh(session, repo_id, "branches", cache_max_age_days):
            return _branches_to_df(get_cached_branches(session, repo_id))

        branches_df = process_branches({"owner": owner, "repo": repo}, token)
        upsert_branches(session, repo_id, branches_df.to_dict("records"))
        record_fetch(session, repo_id, "branches")
        return _normalize_branches_df(branches_df)


def get_commits_data(
    owner,
    repo,
    branch,
    token,
    since_date=None,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    since_ts = _normalize_since_date(since_date)

    if not use_db_cache or session is None or repo_id is None:
        commits_df = _normalize_commits_df(get_commits_cached(owner, repo, branch, token, since_ts))
        if since_ts is not None:
            commits_full_df = _normalize_commits_df(get_commits_cached(owner, repo, branch, token))
        else:
            commits_full_df = commits_df
        return commits_df, commits_full_df

    with st.spinner("Loading commits..."):
        if is_cache_fresh(session, repo_id, "commits", cache_max_age_days):
            commits_full_df = _commits_to_df(get_cached_commits(session, repo_id))
        else:
            commits_full_df = _normalize_commits_df(process_commits(
                {"owner": owner, "repo": repo, "branch": branch},
                token,
            ))
            upsert_commits(session, repo_id, commits_full_df.to_dict("records"))
            record_fetch(session, repo_id, "commits")

        if since_ts is not None:
            commits_df = commits_full_df[commits_full_df["authoredDate"] >= since_ts]
        else:
            commits_df = commits_full_df

        return commits_df, commits_full_df


def get_releases_data(
    owner,
    repo,
    token,
    since_date=None,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    since_ts = _normalize_since_date(since_date)

    if not use_db_cache or session is None or repo_id is None:
        releases_df = get_releases_cached(owner, repo, token, since_ts)
        return _normalize_releases_df(releases_df)

    with st.spinner("Loading releases..."):
        if is_cache_fresh(session, repo_id, "releases", cache_max_age_days):
            releases_df = _releases_to_df(get_cached_releases(session, repo_id, since_ts))
        else:
            releases_df = _normalize_releases_df(process_releases({"owner": owner, "repo": repo}, token))
            upsert_releases(session, repo_id, releases_df.to_dict("records"))
            record_fetch(session, repo_id, "releases")
            if since_ts is not None:
                releases_df = releases_df[releases_df["created_at"] >= since_ts]

        return releases_df


def get_issues_data(
    owner,
    repo,
    token,
    since_date=None,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    since_ts = _normalize_since_date(since_date)

    if not use_db_cache or session is None or repo_id is None:
        issues_df = get_issues_cached(owner, repo, token, since_ts)
        return _normalize_issues_df(issues_df)

    with st.spinner("Loading issues..."):
        if is_cache_fresh(session, repo_id, "issues", cache_max_age_days):
            issues_df = _issues_to_df(get_cached_issues(session, repo_id, since_ts))
        else:
            issues_df = _normalize_issues_df(process_issues({"owner": owner, "repo": repo}, token))
            upsert_issues(session, repo_id, issues_df.to_dict("records"))
            record_fetch(session, repo_id, "issues")
            if since_ts is not None:
                issues_df = issues_df[issues_df["createdAt"] >= since_ts]

        return issues_df


def get_prs_data(
    owner,
    repo,
    token,
    since_date=None,
    use_db_cache=False,
    session=None,
    repo_id=None,
    cache_max_age_days=7,
):
    since_ts = _normalize_since_date(since_date)

    if not use_db_cache or session is None or repo_id is None:
        prs_df = get_prs_cached(owner, repo, token, since_ts)
        return _normalize_prs_df(prs_df)

    with st.spinner("Loading pull requests..."):
        if is_cache_fresh(session, repo_id, "prs", cache_max_age_days):
            prs_df = _prs_to_df(get_cached_prs(session, repo_id, since_ts))
        else:
            prs_df = _normalize_prs_df(process_prs({"owner": owner, "repo": repo}, token))
            upsert_prs(session, repo_id, prs_df.to_dict("records"))
            record_fetch(session, repo_id, "prs")
            if since_ts is not None:
                prs_df = prs_df[prs_df["createdAt"] >= since_ts]

        return prs_df
