"""This is the main module of the data_viewer streamlit app."""

import streamlit as st
import traceback
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

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
from ui import display_repo_info, display_branch_results, display_commit_results, display_release_results, display_issue_results
from data import get_branches_data, get_commits_data, get_releases_data, get_issues_data, get_prs_data
from maturity_tools.analyzers import BranchAnalyzer, CommitAnalyzer, ReleaseAnalyzer, IssuePRAnalyzer
from storage.cache import get_or_create_repo
from storage.db import get_session, init_db

# Import distinguished owners
from distinguished_owners import DISTINGUISHED_OWNERS

import requests

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

def calculate_since_date(time_range):
    """Calculate the 'since' date based on selected time range."""
    now = datetime.now(timezone.utc)
    
    if time_range == "6 months":
        return now - timedelta(days=180)
    elif time_range == "1 year":
        return now - timedelta(days=365)
    elif time_range == "2 years":
        return now - timedelta(days=730)
    elif time_range == "3 years":
        return now - timedelta(days=1095)
    else:  # "All time"
        return None

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
    col_owner, col_repo, col_time = st.columns([2, 2, 2])
    
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
    
    with col_time:
        time_range = st.selectbox(
            "Analysis Time Range",
            ["6 months", "1 year", "2 years", "3 years", "All time"],
            index=0,  # Default to 6 months
            help="Select how far back to analyze data. Shorter ranges load faster for large repositories."
        )
    
    # Calculate the since date for queries
    since_date = calculate_since_date(time_range)
    
    # Display time range info
    if since_date:
        st.info(f"📅 Analyzing data from **{since_date.strftime('%B %d, %Y')}** onwards ({time_range})")
    else:
        st.info("📅 Analyzing **all available data** (this may take longer for large repositories)")

    use_db_cache_default = os.getenv("USE_DB_CACHE", "false").lower() in {"1", "true", "yes"}
    use_db_cache = st.toggle(
        "Use DB cache",
        value=use_db_cache_default,
        help="Use the local database cache (requires DATABASE_URL or default sqlite).",
    )
    session = None
    repo_obj = None
    if use_db_cache:
        try:
            init_db()
            session = get_session()
        except Exception as exc:
            st.warning(f"DB cache unavailable: {exc}")
            use_db_cache = False
    
    info_query_variables = {
        "owner": owner,
        "repo": repo,
    }

    info_result = github_api_call(repo_info_query, info_query_variables, GITHUB_TOKEN)
    if use_db_cache and session:
        default_branch = (
            info_result.get("data", {})
            .get("repository", {})
            .get("defaultBranchRef", {})
            .get("name")
        )
        repo_obj = get_or_create_repo(session, owner, repo, default_branch)
    display_repo_info(info_result)
    st.divider()

    # releases
    releases_df = get_releases_data(
        owner,
        repo,
        GITHUB_TOKEN,
        since_date,
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
        since_date,
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
            since_date,
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
        since_date,
        use_db_cache=use_db_cache,
        session=session,
        repo_id=repo_obj.id if repo_obj else None,
    )
    # if the commits_df is empty, show a warning
    if commits_df.empty:
        st.warning("No commits found for the selected branch and time range.")
    else:
        # st.dataframe(commits_df)
        commit_analyzer = CommitAnalyzer(commits_df, df_commits_full=commits_full_df)
        display_commit_results(commit_analyzer)





if __name__ == "__main__":
    main()
