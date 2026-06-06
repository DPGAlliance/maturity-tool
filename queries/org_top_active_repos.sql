WITH latest_runs AS (
  SELECT
    r.repo_id,
    r.id AS run_id,
    ROW_NUMBER() OVER (
      PARTITION BY r.repo_id
      ORDER BY r.run_started_at DESC, r.id DESC
    ) AS repo_run_rank
  FROM runs r
  JOIN repos repo ON repo.id = r.repo_id
  WHERE repo.owner = :owner
),
latest_activity AS (
  SELECT
    repo.owner,
    repo.name AS repo,
    MAX(CASE WHEN m.name = 'score_90d' THEN m.value_float END) AS activity_score,
    MAX(CASE WHEN m.name = 'commits_90d' THEN m.value_int END) AS commits_90d,
    MAX(CASE WHEN m.name = 'prs_merged_90d' THEN m.value_int END) AS prs_merged_90d,
    MAX(CASE WHEN m.name = 'prs_opened_90d' THEN m.value_int END) AS prs_opened_90d,
    MAX(CASE WHEN m.name = 'issues_closed_90d' THEN m.value_int END) AS issues_closed_90d,
    MAX(CASE WHEN m.name = 'issues_opened_90d' THEN m.value_int END) AS issues_opened_90d,
    MAX(CASE WHEN m.name = 'releases_90d' THEN m.value_int END) AS releases_90d,
    MAX(CASE WHEN m.name = 'last_commit_at' THEN m.value_text END) AS last_commit_at
  FROM repos repo
  LEFT JOIN latest_runs lr
    ON lr.repo_id = repo.id
    AND lr.repo_run_rank = 1
  LEFT JOIN metrics m
    ON m.run_id = lr.run_id
    AND m.scope = 'activity'
  WHERE repo.owner = :owner
  GROUP BY repo.owner, repo.name
),
ranked AS (
  SELECT
    owner,
    repo,
    COALESCE(activity_score, 0) AS activity_score,
    COALESCE(commits_90d, 0) AS commits_90d,
    COALESCE(prs_merged_90d, 0) AS prs_merged_90d,
    COALESCE(prs_opened_90d, 0) AS prs_opened_90d,
    COALESCE(issues_closed_90d, 0) AS issues_closed_90d,
    COALESCE(issues_opened_90d, 0) AS issues_opened_90d,
    COALESCE(releases_90d, 0) AS releases_90d,
    last_commit_at,
    ROW_NUMBER() OVER (
      PARTITION BY owner
      ORDER BY COALESCE(activity_score, 0) DESC, last_commit_at DESC NULLS LAST, repo
    ) AS owner_rank
  FROM latest_activity
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
WHERE owner_rank <= CAST(:top_n AS int)
ORDER BY owner_rank;

/*
Recent activity score method:
- Reads the latest stored activity metrics for each repo.
- `activity.score_90d` is the authoritative ranking value.
- Component counts are included for explanation and prompt grounding.
*/
