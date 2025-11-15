import streamlit as st


def dispay_repo_info(result):
    #parse metrics from result
    repo = result.get("data", {}).get("repository", {})
    branch = repo.get("defaultBranchRef", {}).get("name", "-")
    stargazers = repo.get("stargazerCount", 0)
    forks = repo.get("forkCount", 0)
    watchers = repo.get("watchers", {}).get("totalCount", 0)
    open_issues = repo.get("issues", {}).get("totalCount", 0)
    closed_issues = repo.get("closedIssues", {}).get("totalCount", 0)
    # display metrics
    st.subheader("Repository Summary")
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.metric("Default Branch", branch)
    col2.metric("Stars", stargazers)
    col3.metric("Forks", forks)
    col4.metric("Watchers", watchers)
    col5.metric("Open Issues", open_issues)
    col6.metric("Closed Issues", closed_issues)

def display_brach_results(result_df):
    st.dataframe(result_df)
    