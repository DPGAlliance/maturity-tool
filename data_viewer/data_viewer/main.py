
"""This is the main module of the data_viewer streamlit app."""

import streamlit as st
import traceback
from dotenv import load_dotenv
import os
from maturity_tools.github_call import github_api_call, process_branches
from maturity_tools.queries import repo_info_query
from ui import display_repo_info, display_branch_results, display_commit_results
from data import get_branches_cached, get_commits_cached
from maturity_tools.analyzers import BranchAnalyzer, CommitAnalyzer

load_dotenv()  # Load environment variables from .env file

def main():
    st.set_page_config(layout="wide")
    st.title("Maturity Data Viewer")
    st.write("This app is for showcasing the currently available data from the maturity_tools package.")
    st.write("1. Select your owner/repo pair")

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    col_owner, col_repo = st.columns([2, 2])
    owner = col_owner.text_input("Repository Owner", value="egovernments")
    repo = col_repo.text_input("Repository Name", value="DIGIT-OSS")
    info_query_variables = {
        "owner": owner,
        "repo": repo,
    }

    info_result = github_api_call(repo_info_query, info_query_variables, GITHUB_TOKEN)
    display_repo_info(info_result)
    st.divider()
    
    st.subheader("Branches")
    branches_df = get_branches_cached(owner, repo, GITHUB_TOKEN)
    display_branch_results(branches_df)
    # we could pass the df fisrt to the BranchAnalyzer
    # and mark in the UI df which ones are stale/active
    branch_analyzer = BranchAnalyzer(branches_df)
    days = st.number_input("Days to look back for branch activity", min_value=1, max_value=365, value=30)
    stale, active = branch_analyzer.stale_branches(days)
    st.markdown(f"There are :red[{stale}] stale branches, and :green[{active}] active ones. Looking at the last _{days} days.")
    st.divider()

    # This is all general stuff so far. Lets get into branch specific analysis next.
    default_branch = info_result.get("data", {}).get("repository", {}).get("defaultBranchRef", {}).get("name", "")
    selected_branch = st.selectbox("Select a branch to analyze further", branches_df['branch_name'].tolist(), index=branches_df['branch_name'].tolist().index(default_branch) if default_branch in branches_df['branch_name'].tolist() else 0)
    st.subheader(f"Commits on :green[{selected_branch}] branch")
    commits_df = get_commits_cached(owner, repo, selected_branch, GITHUB_TOKEN)
    # st.dataframe(commits_df)
    commit_analyzer = CommitAnalyzer(commits_df)
    display_commit_results(commit_analyzer)

    





if __name__ == "__main__":
    main()
