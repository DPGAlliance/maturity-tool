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
            st.markdown(f"## New: {new_contributors}   |   Active Core: {core_contributors}")
    
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

def display_release_results(release_analyzer):
    """Display comprehensive release analysis results."""
    
    # Check if we have releases to analyze
    if release_analyzer.df_releases.empty:
        st.warning("No releases found for this repository.")
        return
    
    # Basic release metrics
    col1, col2, col3, col4 = st.columns(4)
    
    # Total releases
    total_releases = len(release_analyzer.df_releases)
    with col1:
        with st.container(border=True):
            st.markdown("**Total Releases**")
            st.markdown(f"## {total_releases}")
    
    # Total downloads
    total_downloads = release_analyzer.total_downloads()
    with col2:
        with st.container(border=True):
            st.markdown("**Total Downloads**")
            if total_downloads >= 1000000:
                downloads_display = f"{total_downloads/1000000:.1f}M"
                downloads_color = "green"
            elif total_downloads >= 1000:
                downloads_display = f"{total_downloads/1000:.1f}K"
                downloads_color = "blue"
            else:
                downloads_display = str(total_downloads)
                downloads_color = "orange"
            st.markdown(f"## :{downloads_color}[{downloads_display}]")
    
    # Latest release info
    latest_release = release_analyzer.df_releases.sort_values('created_at').iloc[-1]
    days_since_latest = (pd.to_datetime('now', utc=True) - latest_release['created_at']).days
    
    with col3:
        with st.container(border=True):
            st.markdown("**Days Since Latest**")
            if days_since_latest <= 30:
                release_freshness_color = "green"
            elif days_since_latest <= 90:
                release_freshness_color = "orange"
            else:
                release_freshness_color = "red"
            st.markdown(f"## :{release_freshness_color}[{days_since_latest}]")
    
    # Average downloads per release
    avg_downloads = total_downloads / total_releases if total_releases > 0 else 0
    with col4:
        with st.container(border=True):
            st.markdown("**Avg Downloads/Release**")
            if avg_downloads >= 10000:
                avg_color = "green"
            elif avg_downloads >= 1000:
                avg_color = "blue"
            else:
                avg_color = "orange"
            if avg_downloads >= 1000:
                avg_display = f"{avg_downloads/1000:.1f}K"
            else:
                avg_display = f"{avg_downloads:.0f}"
            st.markdown(f"## :{avg_color}[{avg_display}]")
    
    # Release timeline analysis
    st.subheader("📅 Release Timeline")
    
    # Period selection for release frequency
    period = st.selectbox("View releases by:", ["month", "year"], index=0, key="release_period")
    
    try:
        release_freq = release_analyzer.releases_by_period(period)
        
        if not release_freq.empty:
            # Display release frequency chart
            st.line_chart(
                data=release_freq.set_index('created_at')['release_count'],
                height=300
            )
            
            # Show release activity stats
            recent_data = release_freq.tail(10)
            avg_releases = recent_data['release_count'].mean()
            max_releases = recent_data['release_count'].max()
            
            col1, col2 = st.columns(2)
            with col1:
                with st.container(border=True):
                    st.markdown(f"**Avg Releases/_{period}_**")
                    st.markdown(f"## {avg_releases:.1f}")
            with col2:
                with st.container(border=True):
                    st.markdown(f"**Peak Releases/_{period}_**")
                    st.markdown(f"## {max_releases}")
            
        else:
            st.info("No release frequency data available.")
            
    except Exception as e:
        st.error(f"Error calculating release frequency: {str(e)}")
    
    # Raw data expander
    with st.expander("🔍 View Raw Release Data"):
        st.dataframe(release_analyzer.df_releases, width="stretch")

def display_issue_results(issue_analyzer):
    """Display comprehensive issue and PR analysis results."""
    st.subheader("Community Engagement")

    # Check if we have issues to analyze
    if issue_analyzer.df_issues.empty and issue_analyzer.df_prs.empty:
        st.warning("No issues or pull requests found for this repository.")
        return
    
    # Basic metrics
    st.markdown("### Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    # Total issues
    total_issues = len(issue_analyzer.df_issues)
    with col1:
        with st.container(border=True):
            st.markdown("**Total Issues**")
            st.markdown(f"## {total_issues}")
    
    # Total PRs
    total_prs = len(issue_analyzer.df_prs)
    with col2:
        with st.container(border=True):
            st.markdown("**Total PRs**")
            st.markdown(f"## {total_prs}")
    
    # Open issues (backlog size)
    open_issues = issue_analyzer.backlog_size()
    with col3:
        with st.container(border=True):
            st.markdown("**Open Issues (Backlog)**")
            if open_issues > 100:
                backlog_color = "red"
            elif open_issues > 50:
                backlog_color = "orange"
            else:
                backlog_color = "green"
            st.markdown(f"## :{backlog_color}[{open_issues}]")
    
    # Issue closure ratio
    closure_ratio = issue_analyzer.issue_closure_ratio(90)
    with col4:
        with st.container(border=True):
            st.markdown("**Issue Closure Ratio (90d)**")
            if closure_ratio >= 0.8:
                closure_color = "green"
            elif closure_ratio >= 0.5:
                closure_color = "orange"
            else:
                closure_color = "red"
            st.markdown(f"## :{closure_color}[{closure_ratio:.2f}]")
    
    # Response & Resolution Times
    st.subheader("⏱️ Response & Resolution Times")
    
    # Determine how many columns we need based on available data
    has_issues = not issue_analyzer.df_issues.empty
    has_prs = not issue_analyzer.df_prs.empty

    if has_issues:
        # create a timeseries line plot that show open issue count over time
        st.markdown("#### Open Issues Over time")
        st.line_chart(issue_analyzer.open_issues_over_time())
    
    if has_issues and has_prs:
        col1, col2, col3, col4 = st.columns(4)
    elif has_issues or has_prs:
        col1, col2 = st.columns(2)
    else:
        st.info("No issues or pull requests data available for response time analysis.")
        return
    
    # Time to first response - Issues (only if we have issues)
    if has_issues:
        time_to_response_issues = issue_analyzer.time_to_first_response('issue')
        response_days_issues = time_to_response_issues.total_seconds() / (24 * 3600)
        with col1:
            with st.container(border=True):
                st.markdown("**Time to First Response (Issues)**")
                if response_days_issues <= 1:
                    response_color = "green"
                elif response_days_issues <= 7:
                    response_color = "orange"
                else:
                    response_color = "red"
                st.markdown(f"## :{response_color}[{response_days_issues:.1f}d]")
    
    # Time to first response - PRs (only if we have PRs)
    if has_prs:
        time_to_response_prs = issue_analyzer.time_to_first_response('pr')
        response_days_prs = time_to_response_prs.total_seconds() / (24 * 3600)
        with (col2 if has_issues else col1):
            with st.container(border=True):
                st.markdown("**Time to First Response (PRs)**")
                if response_days_prs <= 1:
                    pr_response_color = "green"
                elif response_days_prs <= 3:
                    pr_response_color = "orange"
                else:
                    pr_response_color = "red"
                st.markdown(f"## :{pr_response_color}[{response_days_prs:.1f}d]")
    
    # Time to close - Issues (only if we have issues)
    if has_issues:
        time_to_close_issues = issue_analyzer.time_to_close('issue')
        close_days_issues = time_to_close_issues.total_seconds() / (24 * 3600)
        with (col3 if has_prs else col2):
            with st.container(border=True):
                st.markdown("**Time to Close (Issues)**")
                if close_days_issues <= 7:
                    close_color = "green"
                elif close_days_issues <= 30:
                    close_color = "orange"
                else:
                    close_color = "red"
                st.markdown(f"## :{close_color}[{close_days_issues:.1f}d]")
    
    # Time to merge - PRs (only if we have PRs)
    if has_prs:
        time_to_merge = issue_analyzer.pr_merge_time()
        merge_days = time_to_merge.total_seconds() / (24 * 3600)
        with (col4 if has_issues else col2):
            with st.container(border=True):
                st.markdown("**Time to Merge (PRs)**")
                if merge_days <= 3:
                    merge_color = "green"
                elif merge_days <= 14:
                    merge_color = "orange"
                else:
                    merge_color = "red"
                st.markdown(f"## :{merge_color}[{merge_days:.1f}d]")
    
    # Determine columns based on available data
    if has_issues and has_prs:
        col1, col2 = st.columns(2)
    else:
        col1 = st.columns(1)[0]
    
    # Good first issues velocity (only if we have issues)
    if has_issues:
        gfi_velocity = issue_analyzer.good_first_issue_velocity(90)
        with col1:
            with st.container(border=True):
                st.markdown("**Good First Issues Closed (90d)**")
                if gfi_velocity >= 10:
                    gfi_color = "green"
                elif gfi_velocity >= 5:
                    gfi_color = "orange"
                else:
                    gfi_color = "red"
                st.markdown(f"## :{gfi_color}[{gfi_velocity}]")
    
    # Issues & PRs Status Breakdown
    st.subheader("📊 Status Breakdown")
    
    col1, col2 = st.columns(2)
    
    # Issues status breakdown
    with col1:
        st.markdown("**Issues Status**")
        if not issue_analyzer.df_issues.empty:
            issues_status = issue_analyzer.df_issues['state'].value_counts()

            open_issues = issues_status.get('OPEN', 0)
            closed_issues = issues_status.get('CLOSED', 0)
            total_issues = closed_issues + open_issues
            closed_issues_ratio = closed_issues / total_issues if total_issues else 0

            issues_status_df = issues_status.reset_index().rename(columns={'index': 'Status', 'state': 'Count'})
            ratio_df = pd.DataFrame([
                {"Status": "Closed Issues %", "Count": round(closed_issues_ratio, 2)}
            ])
            issues_status_df = pd.concat([issues_status_df, ratio_df], ignore_index=True)
            issues_status_df["Status"] = issues_status_df["Status"].astype(str)
            issues_status_df["Count"] = pd.to_numeric(issues_status_df["Count"], errors="coerce")

            st.dataframe(
                issues_status_df,
                width="stretch",
                hide_index=True
            )
        else:
            st.info("No issue data available")
    
    # PRs status breakdown
    with col2:
        st.markdown("**Pull Requests Status**")
        if not issue_analyzer.df_prs.empty:
            prs_status = issue_analyzer.df_prs['state'].value_counts()
            st.dataframe(
                prs_status.reset_index().rename(columns={'index': 'Status', 'state': 'Count'}),
                width="stretch",
                hide_index=True
            )
        else:
            st.info("No pull requests data available")
