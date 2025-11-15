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