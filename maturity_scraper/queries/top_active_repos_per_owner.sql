-- Edit top_n and the since interval in params to change ranking depth and time window.
WITH params AS (
  SELECT
    10::int AS top_n,
    now() - interval '90 days' AS since
),
recent_commits AS (
  SELECT
    repo_id,
    COUNT(*) FILTER (
      WHERE authored_date >= (SELECT since FROM params)
    ) AS commits_90d,
    MAX(authored_date) AS last_commit_at
  FROM commits
  GROUP BY repo_id
),
recent_prs AS (
  SELECT
    repo_id,
    COUNT(*) FILTER (
      WHERE created_at >= (SELECT since FROM params)
    ) AS prs_opened_90d,
    COUNT(*) FILTER (
      WHERE merged_at >= (SELECT since FROM params)
    ) AS prs_merged_90d
  FROM pull_requests
  GROUP BY repo_id
),
recent_issues AS (
  SELECT
    repo_id,
    COUNT(*) FILTER (
      WHERE created_at >= (SELECT since FROM params)
    ) AS issues_opened_90d,
    COUNT(*) FILTER (
      WHERE closed_at >= (SELECT since FROM params)
    ) AS issues_closed_90d
  FROM issues
  GROUP BY repo_id
),
recent_releases AS (
  SELECT
    repo_id,
    COUNT(*) FILTER (
      WHERE created_at >= (SELECT since FROM params)
    ) AS releases_90d
  FROM releases
  GROUP BY repo_id
),
scored AS (
  SELECT
    r.owner,
    r.name AS repo,
    COALESCE(c.commits_90d, 0) AS commits_90d,
    COALESCE(p.prs_opened_90d, 0) AS prs_opened_90d,
    COALESCE(p.prs_merged_90d, 0) AS prs_merged_90d,
    COALESCE(i.issues_opened_90d, 0) AS issues_opened_90d,
    COALESCE(i.issues_closed_90d, 0) AS issues_closed_90d,
    COALESCE(rel.releases_90d, 0) AS releases_90d,
    c.last_commit_at,
    (
      COALESCE(c.commits_90d, 0) * 0.25 +
      COALESCE(p.prs_merged_90d, 0) * 5.0 +
      COALESCE(p.prs_opened_90d, 0) * 2.0 +
      COALESCE(i.issues_closed_90d, 0) * 2.0 +
      COALESCE(i.issues_opened_90d, 0) * 0.5 +
      COALESCE(rel.releases_90d, 0) * 3.0 +
      CASE
        WHEN c.last_commit_at >= now() - interval '30 days' THEN 10
        WHEN c.last_commit_at >= now() - interval '90 days' THEN 5
        ELSE 0
      END
    ) AS activity_score
  FROM repos r
  LEFT JOIN recent_commits c ON c.repo_id = r.id
  LEFT JOIN recent_prs p ON p.repo_id = r.id
  LEFT JOIN recent_issues i ON i.repo_id = r.id
  LEFT JOIN recent_releases rel ON rel.repo_id = r.id
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY owner
      ORDER BY activity_score DESC, last_commit_at DESC NULLS LAST, repo
    ) AS owner_rank
  FROM scored
)
SELECT
  owner,
  owner_rank,
  repo,
  activity_score,
  commits_90d,
  prs_merged_90d,
  prs_opened_90d,
  issues_closed_90d,
  issues_opened_90d,
  releases_90d,
  last_commit_at
FROM ranked
WHERE owner_rank <= (SELECT top_n FROM params)
ORDER BY owner, owner_rank;

/*
Activity score method:
- Measure recent activity over the window in params.since (default: 90 days).
- Combine several signals: commits, PRs opened, PRs merged, issues opened,
  issues closed, and releases published.
- Weight completed delivery and maintenance higher than raw volume:
  PR merges carry the most weight, releases and closed issues are next,
  opened PRs matter more than opened issues, and commits are weighted lightly
  so a noisy commit stream does not dominate the ranking.
- Add a recency bonus from last_commit_at so recently touched repos outrank
  similarly busy but currently stale repos.
*/
