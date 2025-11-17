import streamlit as st
import pandas as pd


def display_repo_info(result):
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

def display_branch_results(result_df):
    st.dataframe(result_df)

def display_commit_results(commit_analyzer):
    """Display comprehensive commit analysis results."""
    
    # Check if we have commits to analyze
    if commit_analyzer.df_commits.empty:
        st.warning("No commits found for this branch.")
        return
    
    # Basic commit metrics
    # st.markdown("### Commit Metrics")
    col1, col2, col3, col4 = st.columns(4)
    
    # Total commits
    total_commits = len(commit_analyzer.df_commits)
    with col1:
        with st.container(border=True):
            st.markdown("**Total Commits**")
            st.markdown(f"## {total_commits}")
    
    # Staleness
    days_since_last, last_commit_date = commit_analyzer.staleness()
    if days_since_last is not None:
        if days_since_last >= 30:
            staleness_color = "red"
        else:
            staleness_color = "green"
        with col2:
            with st.container(border=True):
                st.markdown("**Staleness**")
                st.markdown(f"## :{staleness_color}[{days_since_last}]")

    # Contributor Analysis
    st.subheader("Contributor Analysis")
    #select lines or commits
    contrib_type_select = st.radio("Select metric type:", ('commits', 'lines'))

    col1, col2, col3, col4 = st.columns(4)

    # total contributors
    total_contributors = commit_analyzer.df_commits['author_login'].nunique()
    with col1:
        with st.container(border=True):
            st.markdown("**Total Contributors**")
            st.markdown(f"## {total_contributors}")
    
    # Bus factor
    bus_factor_commit = commit_analyzer.bus_factor(contrib_type_select)
    if bus_factor_commit < 10:
        bus_color = "red"
    else:
        bus_color = "green"
    with col2:
        with st.container(border=True):
            st.markdown(f"**Bus Factor ({contrib_type_select})**")
            st.markdown(f"## :{bus_color}[{bus_factor_commit}]")

    # New vs Core contributors
    new_contributors, core_contributors = commit_analyzer.new_vs_core_contributors(90, contrib_type_select)
    with col3:
        with st.container(border=True):
            st.markdown(f"**Contributors (90 days) ({contrib_type_select})**")
            st.markdown(f"## New: {new_contributors}   |   Core: {core_contributors}")
    
    # Contributor diversity (HHI)
    hhi = commit_analyzer.contributor_diversity_hhi(contrib_type_select)
    if hhi >= 2500:  # High concentration
        diversity_color = "red"
        diversity_text = "Low"
    elif hhi >= 1500:  # Medium concentration
        diversity_color = "orange"
        diversity_text = "Medium"
    else:  # Low concentration (high diversity)
        diversity_color = "green"
        diversity_text = "High"
    with col4:
        with st.container(border=True):
            st.markdown(f"**Contributor Diversity ({contrib_type_select})**")
            st.markdown(f"## :{diversity_color}[{diversity_text}] ({hhi:.0f})")
    
    # Time-based analysis
    st.subheader("Commit Frequency")
    
    # Commit frequency controls
    period = st.selectbox("View commits by:", ["day", "week", "month"], index=1)
    try:
        commit_freq = commit_analyzer.commit_frequency(period)
        if not commit_freq.empty:
            # Display commit frequency chart
            st.line_chart(
                data=commit_freq.set_index('authoredDate')['commit_count'],
                height=300
            )
            
            # Show recent activity stats
            recent_data = commit_freq.tail(10)
            avg_commits = recent_data['commit_count'].mean()
            max_commits = recent_data['commit_count'].max()
            
            col1, col2 = st.columns(2)
            col1.metric(f"Avg Commits/_{period}_", f"{avg_commits:.1f}")
            col2.metric(f"Peak Commits/_{period}_", f"{max_commits}")
            
        else:
            st.info("No commit frequency data available.")
            
    except Exception as e:
        st.error(f"Error calculating commit frequency: {str(e)}")
    
    # Code churn analysis
    st.subheader("🔄 Code Churn Analysis")
    
    try:
        churn_data = commit_analyzer.code_churn(period)
        
        if not churn_data.empty:
            # Display code churn chart
            st.line_chart(
                data=churn_data.set_index('authoredDate')['code_churn'],
                height=400
            )
            
            # Show churn stats
            recent_churn = churn_data.tail(10)
            avg_churn = recent_churn['code_churn'].mean()
            max_churn = recent_churn['code_churn'].max()
            
            col1, col2 = st.columns(2)
            col1.metric(f"Avg Lines Changed/_{period}_", f"{avg_churn:.0f}")
            col2.metric(f"Peak Lines Changed/_{period}_", f"{max_churn:.0f}")
            
        else:
            st.info("No code churn data available.")
            
    except Exception as e:
        st.error(f"Error calculating code churn: {str(e)}")
    
    # Top contributors
    st.subheader("🏆 Top Contributors")
    
    try:
        # Get top contributors by commits
        top_contributors = (commit_analyzer.df_commits['author_login']
                          .value_counts()
                          .head(10)
                          .reset_index())
        top_contributors.columns = ['Author', 'Commits']
        
        # Display as a nice table
        st.dataframe(
            top_contributors,
            width='stretch',
            hide_index=True
        )
        
    except Exception as e:
        st.error(f"Error displaying contributors: {str(e)}")
    
    # Raw data expander
    with st.expander("🔍 View Raw Commit Data"):
        st.dataframe(commit_analyzer.df_commits, width='stretch')