import streamlit as st
from maturity_tools.github_call import process_branches

# Cache branch results until owner/repo changes
@st.cache_data(show_spinner=True)
def get_branches_cached(owner, repo, token):
    variables = {"owner": owner, "repo": repo}
    return process_branches(variables, token)