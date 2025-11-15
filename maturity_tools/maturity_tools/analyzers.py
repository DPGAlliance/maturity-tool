import pandas as pd

class BranchAnalyzer:
    def __init__(self, df_branches):
        """
        Initializes the BranchAnalyzer with a DataFrame of branches.

        Args:
            df_branches (pd.DataFrame): DataFrame containing branch data with
                                        'last_commit_date' column.
        """
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