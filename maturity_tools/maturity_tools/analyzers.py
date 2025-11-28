import pandas as pd

class BranchAnalyzer:
    def __init__(self, df_branches):
        """
        Initializes the BranchAnalyzer with a DataFrame of branches.

        Args:
            df_branches (pd.DataFrame): DataFrame containing branch data with
                                        'last_commit_date' column.
        """
        if df_branches.empty:
            raise ValueError("Cannot initialize BranchAnalyzer with an empty DataFrame")
        self.df_branches = df_branches.copy()
        self.df_branches['last_commit_date'] = pd.to_datetime(self.df_branches['last_commit_date'])

    def stale_branches(self, days=90):
        """
        Identifies and counts stale branches based on the last commit date.

        Args:
            days (int): The number of days to consider a branch stale if no commits
                        have been made within this period.

        Returns:
            tuple: A tuple containing the count of stale branches and alive branches.
        """
        cutoff_date = pd.to_datetime('now', utc=True) - pd.Timedelta(days=days)
        self.df_branches['is_stale'] = self.df_branches['last_commit_date'] < cutoff_date

        stale_count = self.df_branches['is_stale'].sum()
        alive_count = len(self.df_branches) - stale_count

        return stale_count, alive_count
    

class CommitAnalyzer:
    def __init__(self, df_commits):
        """
        Initializes the CommitAnalyzer with a DataFrame of commits.

        Args:
            df_commits (pd.DataFrame): DataFrame containing commit data with
                                       'authoredDate' column.
        """
        if df_commits.empty:
            raise ValueError("Cannot initialize CommitAnalyzer with an empty DataFrame")
        self.df_commits = df_commits.copy()
        self.df_commits['authoredDate'] = pd.to_datetime(self.df_commits['authoredDate'])


    def commit_frequency(self, period='day'):
        """
        Calculates commit frequency based on the specified time period.

        Args:
            period (str): The time period for aggregation ('day', 'week', 'month').

        Returns:
            pd.DataFrame: DataFrame with commit counts per period.
        """
        if period not in ['day', 'week', 'month']:
            raise ValueError("Period must be 'day', 'week', or 'month'.")

        if period == 'day':
            freq = 'D'
        elif period == 'week':
            freq = 'W'
        else: # period == 'month'
            freq = 'ME'

        commit_counts = self.df_commits.set_index('authoredDate').resample(freq).size().reset_index(name='commit_count')
        return commit_counts


    def staleness(self):
        """
        Calculates the number of days since the last commit.

        Returns:
            tuple: A tuple containing the number of days since the last commit and the date of the last commit.
        """
        if self.df_commits.empty:
            return None, None
        latest_commit_date = self.df_commits['authoredDate'].max()
        days_since_last_commit = (pd.to_datetime('now', utc=True) - latest_commit_date).days
        return days_since_last_commit, latest_commit_date

    def bus_factor(self, contribution_type='commits'):
        """
        Calculates the bus factor based on contributor contributions.

        Args:
            contribution_type (str): Type of contribution to consider ('commits' or 'lines').

        Returns:
            int: The bus factor (number of top contributors whose contributions
                 sum to > 50% of the total).
        """
        if contribution_type not in ['commits', 'lines']:
            raise ValueError("contribution_type must be 'commits' or 'lines'.")

        if contribution_type == 'commits':
            contributions = self.df_commits['author_login'].value_counts().reset_index()
            contributions.columns = ['author_login', 'count']
        else: # contribution_type == 'lines'
            self.df_commits['lines_changed'] = self.df_commits['additions'] + self.df_commits['deletions']
            contributions = self.df_commits.groupby('author_login')['lines_changed'].sum().reset_index()
            contributions.columns = ['author_login', 'count']

        contributions = contributions.sort_values(by='count', ascending=False)
        total_contributions = contributions['count'].sum()
        cumulative_contributions = contributions['count'].cumsum()
        bus_factor = (cumulative_contributions <= total_contributions * 0.5).sum() + 1

        return bus_factor

    def contributor_diversity_hhi(self, contribution_type='commits'):
        """
        Calculates the Contributor Diversity using the Herfindahl-Hirschman Index (HHI).

        Args:
            contribution_type (str): Type of contribution to consider ('commits' or 'lines').

        Returns:
            float: The Herfindahl-Hirschman Index (HHI) score.
        """
        if contribution_type not in ['commits', 'lines']:
            raise ValueError("contribution_type must be 'commits' or 'lines'.")

        if contribution_type == 'commits':
            contributions = self.df_commits['author_login'].value_counts().reset_index()
            contributions.columns = ['author_login', 'count']
        else: # contribution_type == 'lines'
            self.df_commits['lines_changed'] = self.df_commits['additions'] + self.df_commits['deletions']
            contributions = self.df_commits.groupby('author_login')['lines_changed'].sum().reset_index()
            contributions.columns = ['author_login', 'count']

        total_contributions = contributions['count'].sum()
        contributions['percentage'] = (contributions['count'] / total_contributions) * 100
        hhi = (contributions['percentage'] ** 2).sum()

        return hhi

    def new_vs_core_contributors(self, period_days=90, contribution_type='commits'):
        """
        Identifies new and core contributors within a specified period.

        Args:
            period_days (int): The number of days for the "new contributor" period.
            contribution_type (str): Type of contribution to consider for bus factor ('commits' or 'lines').

        Returns:
            tuple: A tuple containing the count of new contributors and core contributors.
        """
        if contribution_type not in ['commits', 'lines']:
            raise ValueError("contribution_type must be 'commits' or 'lines'.")

        # Identify core contributors (based on bus factor)
        if contribution_type == 'commits':
            contributions = self.df_commits['author_login'].value_counts().reset_index()
            contributions.columns = ['author_login', 'count']
        else: # contribution_type == 'lines'
            self.df_commits['lines_changed'] = self.df_commits['additions'] + self.df_commits['deletions']
            contributions = self.df_commits.groupby('author_login')['lines_changed'].sum().reset_index()
            contributions.columns = ['author_login', 'count']

        contributions = contributions.sort_values(by='count', ascending=False)
        total_contributions = contributions['count'].sum()
        cumulative_contributions = contributions['count'].cumsum()
        core_contributors_df = contributions[cumulative_contributions <= total_contributions * 0.5]
        core_contributors = core_contributors_df['author_login'].tolist()

        # Identify new contributors within the period
        latest_date = self.df_commits['authoredDate'].max()
        cutoff_date = latest_date - pd.Timedelta(days=period_days)

        new_contributors = set()
        all_contributors_before_period = set(self.df_commits[self.df_commits['authoredDate'] < cutoff_date]['author_login'].unique())

        for index, row in self.df_commits[self.df_commits['authoredDate'] >= cutoff_date].iterrows():
            author = row['author_login']
            if author not in all_contributors_before_period:
                new_contributors.add(author)

        return len(new_contributors), len(core_contributors)

    def code_churn(self, period='day'):
        """
        Calculates code churn (sum of additions and deletions) based on the specified time period.

        Args:
            period (str): The time period for aggregation ('day', 'week', 'month').

        Returns:
            pd.DataFrame: DataFrame with code churn per period.
        """
        if period not in ['day', 'week', 'month']:
            raise ValueError("Period must be 'day', 'week', or 'month'.")

        if period == 'day':
            freq = 'D'
        elif period == 'week':
            freq = 'W'
        else: # period == 'month'
            freq = 'ME'

        self.df_commits['lines_changed'] = self.df_commits['additions'] + self.df_commits['deletions']
        code_churn_counts = self.df_commits.set_index('authoredDate').resample(freq)['lines_changed'].sum().reset_index(name='code_churn')
        return code_churn_counts
    
class ReleaseAnalyzer:
    def __init__(self, df_releases):
        """
        Initializes the ReleaseAnalyzer with a DataFrame of releases.

        Args:
            df_releases (pd.DataFrame): DataFrame containing release data with
                                        'created_at' and 'total_downloads' columns.
        """
        if df_releases.empty:
            raise ValueError("Cannot initialize ReleaseAnalyzer with an empty DataFrame")
        self.df_releases = df_releases.copy()
        self.df_releases['created_at'] = pd.to_datetime(self.df_releases['created_at'])

    def total_downloads(self):
        """
        Calculates the total download count across all releases.

        Returns:
            int: The total number of downloads.
        """
        return self.df_releases['total_downloads'].sum()

    def releases_by_period(self, period='month'):
        """
        Aggregates the number of releases based on the specified time period.

        Args:
            period (str): The time period for aggregation ('day', 'week', 'month', 'year').

        Returns:
            pd.DataFrame: DataFrame with release counts per period.
        """
        if period not in ['day', 'week', 'month', 'year']:
            raise ValueError("Period must be 'day', 'week', 'month', or 'year'.")

        if period == 'day':
            freq = 'D'
        elif period == 'week':
            freq = 'W'
        elif period == 'month':
            freq = 'ME'
        else: # period == 'year'
            freq = 'YE'

        release_counts = self.df_releases.set_index('created_at').resample(freq).size().reset_index(name='release_count')
        return release_counts


class IssuePRAnalyzer:
    def __init__(self, df_issues, df_prs):
        """
        Initializes the IssuePRAnalyzer with DataFrames of issues and pull requests.

        Args:
            df_issues (pd.DataFrame): DataFrame containing issue data.
            df_prs (pd.DataFrame): DataFrame containing pull request data.
        """
        if df_issues.empty and df_prs.empty:
            raise ValueError("Cannot initialize IssuePRAnalyzer with both issues and PRs DataFrames empty")
        self.df_issues = df_issues.copy()
        self.df_prs = df_prs.copy()

    def time_to_first_response(self, item_type='issue'):
        """
        Calculates the median time to first non-author comment for issues or PRs.

        Args:
            item_type (str): 'issue' or 'pr' to specify which data to analyze.

        Returns:
            pd.Timedelta: Median time to first response.
        """
        if item_type == 'issue':
            df = self.df_issues
            created_col = 'createdAt'
            comment_created_col = 'first_comment_createdAt'
            author_col = 'author_login'
            comment_author_col = 'first_comment_author'
        elif item_type == 'pr':
            df = self.df_prs
            created_col = 'createdAt'
            comment_created_col = 'first_comment_createdAt'
            author_col = 'author_login'
            comment_author_col = 'first_comment_author'
        else:
            raise ValueError("item_type must be 'issue' or 'pr'.")

        # Filter for items with a first comment by a non-author
        responded_items = df[
            (df[comment_created_col].notna()) & 
            (df[comment_author_col] != df[author_col])
        ].copy()

        if responded_items.empty:
            return pd.Timedelta(seconds=0) # Return 0 timedelta if no responses

        time_diff = responded_items[comment_created_col] - responded_items[created_col]
        return time_diff.median()

    def issue_closure_ratio(self, period_days=90):
        """
        Calculates the ratio of closed issues to opened issues within a specified period.

        Args:
            period_days (int): The number of days for the analysis period.

        Returns:
            float: Issue closure ratio.
        """
        end_date = pd.to_datetime('now', utc=True)
        start_date = end_date - pd.Timedelta(days=period_days)

        opened_in_period = self.df_issues[
            (self.df_issues['createdAt'] >= start_date) & 
            (self.df_issues['createdAt'] <= end_date)
        ].shape[0]

        closed_in_period = self.df_issues[
            (self.df_issues['closedAt'].notna()) & 
            (self.df_issues['closedAt'] >= start_date) & 
            (self.df_issues['closedAt'] <= end_date)
        ].shape[0]

        if opened_in_period == 0:
            return 0.0
        return closed_in_period / opened_in_period

    def time_to_close(self, item_type='issue'):
        """
        Calculates the median time to close for issues or PRs.

        Args:
            item_type (str): 'issue' or 'pr' to specify which data to analyze.

        Returns:
            pd.Timedelta: Median time to close.
        """
        if item_type == 'issue':
            df = self.df_issues[self.df_issues['state'] == 'CLOSED'].copy()
            created_col = 'createdAt'
            closed_col = 'closedAt'
        elif item_type == 'pr':
            df = self.df_prs[
                (self.df_prs['state'] == 'MERGED') | (self.df_prs['state'] == 'CLOSED')
            ].copy()
            created_col = 'createdAt'
            closed_col = 'closedAt'
        else:
            raise ValueError("item_type must be 'issue' or 'pr'.")

        if df.empty:
            return pd.Timedelta(seconds=0)

        time_diff = df[closed_col] - df[created_col]
        return time_diff.median()

    def pr_merge_time(self):
        """
        Calculates the median time from PR creation to merge.

        Returns:
            pd.Timedelta: Median time to merge.
        """
        merged_prs = self.df_prs[self.df_prs['state'] == 'MERGED'].copy()
        if merged_prs.empty:
            return pd.Timedelta(seconds=0)
        
        time_diff = merged_prs['mergedAt'] - merged_prs['createdAt']
        return time_diff.median()

    def backlog_size(self):
        """
        Returns the current number of open issues.

        Returns:
            int: Number of open issues.
        """
        return self.df_issues[self.df_issues['state'] == 'OPEN'].shape[0]

    def good_first_issue_velocity(self, period_days=90):
        """
        Calculates the velocity of 'good first issues' being closed within a period.

        Args:
            period_days (int): The number of days for the analysis period.

        Returns:
            float: 'Good first issue' velocity.
        """
        end_date = pd.to_datetime('now', utc=True)
        start_date = end_date - pd.Timedelta(days=period_days)

        good_first_issues_closed = self.df_issues[
            (self.df_issues['state'] == 'CLOSED') & 
            (self.df_issues['labels'].apply(lambda x: 'good first issue' in [label.lower() for label in x])) & 
            (self.df_issues['closedAt'] >= start_date) & 
            (self.df_issues['closedAt'] <= end_date)
        ].shape[0]
        
        # Velocity is count per period, so no division by days here unless specified to be rate per day
        return good_first_issues_closed
    
    def open_issues_over_time(self):
        """
        Generates a time series of open issue counts over time.

        Returns:
            pd.Series: Time series with dates as index and open issue counts as values.
        """
        if self.df_issues.empty:
            return pd.Series(dtype=int)

        # Create a date range from the earliest issue creation to today
        start_date = self.df_issues['createdAt'].min().normalize()
        end_date = pd.to_datetime('now', utc=True).normalize()
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')

        open_issue_counts = []

        for single_date in date_range:
            open_issues = self.df_issues[
                (self.df_issues['createdAt'] <= single_date) & 
                ((self.df_issues['closedAt'].isna()) | (self.df_issues['closedAt'] > single_date))
            ].shape[0]
            open_issue_counts.append(open_issues)

        return pd.Series(data=open_issue_counts, index=date_range, name='open_issue_count')