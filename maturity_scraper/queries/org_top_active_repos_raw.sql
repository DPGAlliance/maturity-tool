WITH params AS (
  SELECT
    :owner AS owner,
    CAST(:top_n AS int) AS top_n,
    now() - make_interval(days => CAST(:since_days AS int)) AS since
),
recent_commits AS (
  SELECT
    c.repo_id,
    COUNT(*) FILTER (
      WHERE c.authored_date >= (SELECT since FROM params)
    ) AS commits_recent,
    MAX(c.authored_date) AS last_commit_at
  FROM commits c
  GROUP BY c.repo_id
),
recent_prs AS (
  SELECT
    pr.repo_id,
    COUNT(*) FILTER (
      WHERE pr.created_at >= (SELECT since FROM params)
    ) AS prs_opened_recent,
    COUNT(*) FILTER (
      WHERE pr.merged_at >= (SELECT since FROM params)
    ) AS prs_merged_recent
  FROM pull_requests pr
  GROUP BY pr.repo_id
),
recent_issues AS (
  SELECT
    i.repo_id,
    COUNT(*) FILTER (
      WHERE i.created_at >= (SELECT since FROM params)
    ) AS issues_opened_recent,
    COUNT(*) FILTER (
      WHERE i.closed_at >= (SELECT since FROM params)
    ) AS issues_closed_recent
  FROM issues i
  GROUP BY i.repo_id
),
recent_releases AS (
  SELECT
    rel.repo_id,
    COUNT(*) FILTER (
      WHERE rel.created_at >= (SELECT since FROM params)
    ) AS releases_recent
  FROM releases rel
  GROUP BY rel.repo_id
),
scored AS (
  SELECT
    r.owner,
    r.name AS repo,
    COALESCE(c.commits_recent, 0) AS commits_recent,
    COALESCE(p.prs_opened_recent, 0) AS prs_opened_recent,
    COALESCE(p.prs_merged_recent, 0) AS prs_merged_recent,
    COALESCE(i.issues_opened_recent, 0) AS issues_opened_recent,
    COALESCE(i.issues_closed_recent, 0) AS issues_closed_recent,
    COALESCE(rel.releases_recent, 0) AS releases_recent,
    c.last_commit_at,
    (
      COALESCE(c.commits_recent, 0) * 0.25 +
      COALESCE(p.prs_merged_recent, 0) * 5.0 +
      COALESCE(p.prs_opened_recent, 0) * 2.0 +
      COALESCE(i.issues_closed_recent, 0) * 2.0 +
      COALESCE(i.issues_opened_recent, 0) * 0.5 +
      COALESCE(rel.releases_recent, 0) * 3.0 +
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
  WHERE r.owner = (SELECT owner FROM params)
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
  commits_recent,
  prs_merged_recent,
  prs_opened_recent,
  issues_closed_recent,
  issues_opened_recent,
  releases_recent,
  last_commit_at
FROM ranked
WHERE owner_rank <= (SELECT top_n FROM params)
ORDER BY owner_rank;

/*
Recent activity score method:
- Measure activity over the last :since_days days.
- Combine recent commits, PRs opened/merged, issues opened/closed, and releases.
- Weight completed delivery and maintenance higher than raw volume.
- Add a recency bonus from last_commit_at so recently touched repos rank above
  similarly active but stale repos.
*/
