from maturity_tools.github_call import process_commits, process_branches, process_releases, process_issues, process_prs
import streamlit as st

# Cache branch results until owner/repo changes
@st.cache_data(show_spinner=True)
def get_branches_cached(owner, repo, token):
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
