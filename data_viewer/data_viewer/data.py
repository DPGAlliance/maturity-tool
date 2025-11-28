from maturity_tools.github_call import process_commits, process_branches, process_releases, process_issues, process_prs
import streamlit as st

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
