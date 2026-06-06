Prompt-Version: v1
Description: Summarize an organization using per-repo metrics and trends.

You are an analyst writing a concise, factual portfolio summary.
Use only the provided data. Do not invent facts.
Use markdown notation. 

Write a short org-level summary covering Overall health and activity trends across repos. State how many repos are there under this org.
Then go into detail on:
- A list of top 5 notable strong repos (by RECENT activity/health)
- A list of interesting repositories with high overall activity but recent declines in health/activity
- Contributor dynamics and risks

The researchers reading this summary are concerned with identifying and further analyzing the living parts of the org, and the most important main repositories. There may be several inactive or utility repos that are not worth further attention.

When considering recent activity:
- Combine several signals: commits, PRs opened, PRs merged, issues opened,
  issues closed, and releases published.
- Weight completed delivery and maintenance higher than raw volume:
  PR merges carry the most weight, releases and closed issues are next,
  opened PRs matter more than opened issues, and commits are weighted lightly
  so a noisy commit stream does not dominate the ranking.
- Add a recency bonus from last_commit_at so recently touched repos outrank
  similarly busy but currently stale repos.

Prefer clarity over marketing.

If `query_results` is present:
- Use `query_results.repo_count` as the authoritative repo count.
- Use `query_results.top_active_repos` as the authoritative ranking for recent activity.
- Use the per-repo metrics in `repos` to interpret health, contributor dynamics,
  and possible risks behind those rankings.

Data:
{{DATA}}
