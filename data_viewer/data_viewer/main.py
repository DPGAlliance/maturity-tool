"""This is the main module of the data_viewer streamlit app."""

import streamlit as st
import traceback
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
import pandas as pd

# Handle imports for both local development and Streamlit Cloud deployment
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
maturity_tools_dir = os.path.join(repo_root, 'maturity_tools')

# Add all necessary paths for imports
sys.path.insert(0, current_dir)           # For ui, data modules
sys.path.insert(0, repo_root)             # For top-level imports
sys.path.insert(0, maturity_tools_dir)    # For maturity_tools package

from maturity_tools.github_call import github_api_call
from maturity_tools.queries import repo_info_query
from maturity_tools.github_call import process_branches, process_commits, process_issues, process_prs, process_releases
from ui import display_repo_info, display_branch_results, display_commit_results, display_release_results, display_issue_results, display_summary
from data import get_branches_data, get_commits_data, get_releases_data, get_issues_data, get_prs_data, get_repo_summary_db, get_org_summary_db
from maturity_tools.analyzers import BranchAnalyzer, CommitAnalyzer, ReleaseAnalyzer, IssuePRAnalyzer
from storage.cache import get_or_create_repo, get_last_fetch_at, has_cache_entry, record_fetch, upsert_branches, upsert_commits, upsert_issues, upsert_prs, upsert_releases
from storage.db import get_session, init_db

# Import distinguished owners
from distinguished_owners import DISTINGUISHED_OWNERS

import requests


ENTITY_TYPES = ("branches", "commits", "issues", "prs", "releases")


def _normalize_datetime_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def _format_last_fetch(dt: datetime | None) -> str:
    if not dt:
        return "(none)"
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)

def fetch_repos_for_owner(owner, token):
    """Fetch public repos for a given owner using GitHub REST API."""
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

def main():
    load_dotenv()
    st.set_page_config(layout="wide")
    st.title("Maturity Data Viewer")
    st.write("This app is for showcasing the currently available data from the maturity_tools package.")

    # Get GitHub token from Streamlit secrets
    GITHUB_TOKEN = st.secrets.get("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        st.error("⚠️ GitHub token not found! Please add GITHUB_TOKEN to Streamlit secrets.")
        st.stop()
    
    # Repository selection
    st.subheader("Repository Selection")
    with st.container():
        col_owner, col_repo, col_source = st.columns([3, 3, 1])

        with col_owner:
            # Provide suggestions via selectbox but allow a free-text owner by choosing "Other"
            owner_choice = st.selectbox(
                "Repository Owner (pick suggestion or choose Other to type)",
                options=list(DISTINGUISHED_OWNERS) + ["Other (type custom owner...)"],
                index=0,
                key="owner_select",
                help="Pick from suggestions or choose Other to type a custom owner."
            )
            if owner_choice and owner_choice.startswith("Other"):
                owner = st.text_input(
                    "Custom owner (type a GitHub user or org)",
                    value="",
                    key="owner_custom",
                    help="Type the organization or username you want to analyze."
                )
            else:
                owner = owner_choice

        with col_repo:
            repo_list = []
            if owner:
                repo_list = fetch_repos_for_owner(owner, GITHUB_TOKEN)
            repo = st.selectbox(
                "Repository Name",
                repo_list if repo_list else ["DIGIT-OSS"],
                index=0 if repo_list else 0
            )

        with col_source:
            # Spacer so the button aligns visually with the dropdowns.
            st.markdown("<div style='height: 0.25rem'></div>", unsafe_allow_html=True)
            if owner and repo:
                source_url = f"https://github.com/{owner}/{repo}"
                link_button = getattr(st, "link_button", None)
                if callable(link_button):
                    link_button("Go to source", source_url)
                else:
                    st.markdown(f"[Go to source]({source_url})")

    # Banner should be outside the selection container.
    last_fetch_placeholder = st.empty()

    # DB cache is the default. If DB is unavailable, fall back to live fetch.
    use_db_cache = True
    session = None
    repo_obj = None
    try:
        init_db()
        session = get_session()
    except Exception as exc:
        st.warning(f"DB cache unavailable; using live fetch. ({exc})")
        use_db_cache = False
    
    info_query_variables = {
        "owner": owner,
        "repo": repo,
    }

    info_result = github_api_call(repo_info_query, info_query_variables, GITHUB_TOKEN)

    default_branch = (
        info_result.get("data", {})
        .get("repository", {})
        .get("defaultBranchRef", {})
        .get("name")
    )

    if use_db_cache and session:
        repo_obj = get_or_create_repo(session, owner, repo, default_branch)
        last_fetch_at = get_last_fetch_at(session, repo_obj.id)
        last_fetch_placeholder.info(
            f"Repository data last updated at: {_format_last_fetch(last_fetch_at)}"
        )

        if not has_cache_entry(session, repo_obj.id):
            with st.spinner("Fetching and caching repo data..."):
                branches_df = process_branches({"owner": owner, "repo": repo}, GITHUB_TOKEN)
                commits_df_full = process_commits({"owner": owner, "repo": repo, "branch": default_branch}, GITHUB_TOKEN)
                issues_df = process_issues({"owner": owner, "repo": repo}, GITHUB_TOKEN)
                prs_df = process_prs({"owner": owner, "repo": repo}, GITHUB_TOKEN)
                releases_df = process_releases({"owner": owner, "repo": repo}, GITHUB_TOKEN)

                branches_df = _normalize_datetime_columns(branches_df, ["last_commit_date"])
                commits_df_full = _normalize_datetime_columns(commits_df_full, ["authoredDate"])
                issues_df = _normalize_datetime_columns(issues_df, ["createdAt", "closedAt", "first_comment_createdAt"])
                prs_df = _normalize_datetime_columns(prs_df, ["createdAt", "mergedAt", "closedAt", "first_comment_createdAt"])
                releases_df = _normalize_datetime_columns(releases_df, ["created_at"])

                upsert_branches(session, repo_obj.id, branches_df.to_dict("records"))
                upsert_commits(session, repo_obj.id, commits_df_full.to_dict("records"))
                upsert_issues(session, repo_obj.id, issues_df.to_dict("records"))
                upsert_prs(session, repo_obj.id, prs_df.to_dict("records"))
                upsert_releases(session, repo_obj.id, releases_df.to_dict("records"))

                for entity in ENTITY_TYPES:
                    record_fetch(session, repo_obj.id, entity)

            last_fetch_at = get_last_fetch_at(session, repo_obj.id)
            last_fetch_placeholder.info(
                f"Repository data last updated at: {_format_last_fetch(last_fetch_at)}"
            )

    display_repo_info(info_result)
    st.divider()

    if use_db_cache and session:
        org_summary = get_org_summary_db(session, owner)
        if org_summary:
            display_summary(org_summary)

        repo_summary = get_repo_summary_db(session, owner, repo)
        display_summary(repo_summary, missing_message="No summary yet.")
        st.divider()

    # releases
    releases_df = get_releases_data(
        owner,
        repo,
        GITHUB_TOKEN,
        use_db_cache=use_db_cache,
        session=session,
        repo_id=repo_obj.id if repo_obj else None,
    )
    if releases_df.empty:
        st.warning("No releases found for the selected time range.")
    else:
        st.subheader("📦 Releases")
        release_analyzer = ReleaseAnalyzer(releases_df)
        display_release_results(release_analyzer)

    # issues and PRs (Community Engagement)
    st.divider()
    st.subheader("Issues & Pull Requests")
    issues_df = get_issues_data(
        owner,
        repo,
        GITHUB_TOKEN,
        use_db_cache=use_db_cache,
        session=session,
        repo_id=repo_obj.id if repo_obj else None,
    )
    if issues_df.empty:
        st.warning("No issues found for the selected time range.")
    else:
        prs_df = get_prs_data(
            owner,
            repo,
            GITHUB_TOKEN,
            use_db_cache=use_db_cache,
            session=session,
            repo_id=repo_obj.id if repo_obj else None,
        )
        issue_analyzer = IssuePRAnalyzer(issues_df, prs_df)
        display_issue_results(issue_analyzer)

    # branches
    st.subheader("Branches")
    branches_df = get_branches_data(
        owner,
        repo,
        GITHUB_TOKEN,
        use_db_cache=use_db_cache,
        session=session,
        repo_id=repo_obj.id if repo_obj else None,
    )
    display_branch_results(branches_df)
    # we could pass the df fisrt to the BranchAnalyzer
    # and mark in the UI df which ones are stale/active
    branch_analyzer = BranchAnalyzer(branches_df)
    days = st.number_input("Days to look back for branch activity", min_value=1, max_value=365, value=30)
    stale, active = branch_analyzer.stale_branches(days)
    st.markdown(f"There are :red[{stale}] stale branches, and :green[{active}] active ones. Looking at the last {days} days.")
    st.divider()

    # Branch specific commit analysis
    default_branch = info_result.get("data", {}).get("repository", {}).get("defaultBranchRef", {}).get("name", "")
    selected_branch = st.selectbox("Select a branch to analyze further", branches_df['branch_name'].tolist(), index=branches_df['branch_name'].tolist().index(default_branch) if default_branch in branches_df['branch_name'].tolist() else 0)
    st.subheader(f"Commits on :green[{selected_branch}] branch")
    commits_df, commits_full_df = get_commits_data(
        owner,
        repo,
        selected_branch,
        GITHUB_TOKEN,
        use_db_cache=use_db_cache,
        session=session,
        repo_id=repo_obj.id if repo_obj else None,
    )
    # if the commits_df is empty, show a warning
    if commits_df.empty:
        st.warning("No commits found for the selected branch.")
    else:
        # st.dataframe(commits_df)
        commit_analyzer = CommitAnalyzer(commits_df, df_commits_full=commits_full_df)
        display_commit_results(commit_analyzer)





if __name__ == "__main__":
    main()
