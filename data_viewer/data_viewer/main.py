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
from data import (
    get_branches_data,
    get_commits_data,
    get_owner_repos_by_activity,
    get_repo_scan_job,
    get_releases_data,
    get_issues_data,
    get_prs_data,
    get_repo_metrics_db,
    get_repo_summary_db,
    get_org_summary_db,
)
from maturity_tools.analyzers import BranchAnalyzer, CommitAnalyzer, ReleaseAnalyzer, IssuePRAnalyzer
from storage.cache import get_or_create_repo, get_last_fetch_at, has_cache_entry, record_fetch, upsert_branches, upsert_commits, upsert_issues, upsert_prs, upsert_releases
from storage.db import get_session, init_db
from storage.secrets import get_secret

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


def _query_param(name: str) -> str | None:
    try:
        value = st.query_params.get(name)
    except Exception:
        return None
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return str(value)


def _parse_direct_repo_target() -> tuple[str | None, str | None, str | None, str | None, int | None]:
    provider = _query_param("provider")
    repo_path = _query_param("repo_path")
    owner = _query_param("owner")
    repo = _query_param("repo")
    scan_id_raw = _query_param("scan_id")
    scan_id = int(scan_id_raw) if scan_id_raw and scan_id_raw.isdigit() else None

    if provider and repo_path and provider == "github":
        parts = [part for part in repo_path.split("/") if part]
        if len(parts) == 2:
            owner = parts[0]
            repo = parts[1]

    if owner and repo:
        return provider or "github", repo_path or f"{owner}/{repo}", owner, repo, scan_id
    return None, None, None, None, scan_id

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

    # Prefer Streamlit secrets (local dev / Streamlit Cloud), then Docker secrets / env.
    # NOTE: Accessing st.secrets will raise if no secrets.toml exists, so guard it.
    try:
        token_from_streamlit = st.secrets.get("GITHUB_TOKEN")
    except Exception:
        token_from_streamlit = None
    GITHUB_TOKEN = token_from_streamlit or get_secret("GITHUB_TOKEN")
    
    if not GITHUB_TOKEN:
        st.error(
            "⚠️ GitHub token not found! Provide GITHUB_TOKEN via Streamlit secrets, env var, or GITHUB_TOKEN_FILE."
        )
        st.stop()

    direct_provider, direct_repo_path, direct_owner, direct_repo, direct_scan_id = _parse_direct_repo_target()
    direct_mode = bool(direct_owner and direct_repo)

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

    if direct_mode and not use_db_cache:
        st.error("Direct result links require the database-backed viewer to be available.")
        st.stop()

    if direct_mode and direct_provider != "github":
        st.error(f"Direct result links currently support GitHub only. Provider received: {direct_provider}")
        st.stop()

    if direct_mode and session and direct_scan_id is not None:
        scan_job = get_repo_scan_job(session, direct_scan_id)
        if scan_job is None:
            st.error("This scan link does not reference a known repo scan job.")
            st.stop()
        if scan_job.provider != "github":
            st.error(f"This scan link uses an unsupported provider: {scan_job.provider}")
            st.stop()
        if scan_job.owner:
            direct_owner = scan_job.owner
        if scan_job.repo:
            direct_repo = scan_job.repo

        if scan_job.status in {"pending", "running"}:
            stage_message = f" Current stage: {scan_job.stage}." if scan_job.stage else ""
            summary_message = ""
            if scan_job.summary_status == "running":
                summary_message = " Repo summary is being generated."
            st.info(f"Scan status: {scan_job.status}.{stage_message}{summary_message} Results are not ready yet.")
            if scan_job.started_at:
                st.caption(f"Started: {scan_job.started_at:%Y-%m-%d %H:%M UTC}")
            st.stop()
        if scan_job.status == "failed":
            st.error(f"Scan failed: {scan_job.error_message or 'Unknown error'}")
            st.stop()

    if direct_mode:
        owner = direct_owner
        repo = direct_repo
        st.caption(f"Direct result view for {owner}/{repo}")
        source_url = f"https://github.com/{owner}/{repo}"
        link_button = getattr(st, "link_button", None)
        if callable(link_button):
            link_button("Go to source", source_url)
        else:
            st.markdown(f"[Go to source]({source_url})")
    else:
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
                    if use_db_cache and session:
                        repo_list = get_owner_repos_by_activity(session, owner)
                    else:
                        repo_list = fetch_repos_for_owner(owner, GITHUB_TOKEN)

                if repo_list:
                    repo = st.selectbox(
                        "Repository Name",
                        repo_list,
                        index=0,
                    )
                else:
                    repo = None
                    st.selectbox(
                        "Repository Name",
                        ["No cached repos yet" if use_db_cache and session else "No repos found"],
                        index=0,
                        disabled=True,
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

        if not owner or not repo:
            if owner and use_db_cache and session:
                st.info("No cached repos yet for this owner. Wait for the next refresh.")
            st.stop()

    # Banner should be outside the selection container.
    last_fetch_placeholder = st.empty()
    
    info_result = None
    repo_metrics = None
    default_branch = None

    if use_db_cache and session:
        repo_obj = get_or_create_repo(session, owner, repo, None)
        if repo_obj.default_branch:
            default_branch = repo_obj.default_branch

        last_fetch_at = get_last_fetch_at(session, repo_obj.id)
        last_fetch_placeholder.info(
            f"Repository data last updated at: {_format_last_fetch(last_fetch_at)}"
        )

        if not has_cache_entry(session, repo_obj.id):
            info_query_variables = {
                "owner": owner,
                "repo": repo,
            }
            info_result = github_api_call(
                repo_info_query,
                info_query_variables,
                GITHUB_TOKEN,
                request_name="repo_info",
            )
            default_branch = (
                info_result.get("data", {})
                .get("repository", {})
                .get("defaultBranchRef", {})
                .get("name")
            )
            if default_branch and repo_obj.default_branch != default_branch:
                repo_obj.default_branch = default_branch
                session.add(repo_obj)
                session.commit()

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
        else:
            repo_metrics = get_repo_metrics_db(session, owner, repo)
    else:
        info_query_variables = {
            "owner": owner,
            "repo": repo,
        }
        info_result = github_api_call(
            repo_info_query,
            info_query_variables,
            GITHUB_TOKEN,
            request_name="repo_info",
        )
        default_branch = (
            info_result.get("data", {})
            .get("repository", {})
            .get("defaultBranchRef", {})
            .get("name")
        )

    display_repo_info(info_result or repo_metrics)
    st.divider()

    if use_db_cache and session:
        org_summary = get_org_summary_db(session, owner)
        if org_summary:
            display_summary(org_summary)

        repo_summary = get_repo_summary_db(session, owner, repo)
        scan_job_for_summary = None
        if direct_mode and direct_scan_id is not None:
            scan_job_for_summary = get_repo_scan_job(session, direct_scan_id)
        missing_summary_message = "No summary yet."
        if direct_mode and direct_scan_id is not None:
            if scan_job_for_summary and scan_job_for_summary.summary_status == "failed":
                missing_summary_message = (
                    "We’re sorry, the repo summary could not be generated for this scan. "
                    "The repository metrics and charts are still available below."
                )
        if scan_job_for_summary and scan_job_for_summary.summary_status == "failed":
            display_summary(None, missing_message=missing_summary_message)
        else:
            display_summary(repo_summary, missing_message=missing_summary_message)
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
    default_branch = default_branch or ""
    selected_branch = st.selectbox(
        "Select a branch to analyze further",
        branches_df['branch_name'].tolist(),
        index=branches_df['branch_name'].tolist().index(default_branch)
        if default_branch in branches_df['branch_name'].tolist()
        else 0,
    )
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
