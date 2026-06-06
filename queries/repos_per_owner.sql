SELECT
  owner,
  COUNT(*) AS repo_count
FROM repos
GROUP BY owner
ORDER BY repo_count DESC, owner;
