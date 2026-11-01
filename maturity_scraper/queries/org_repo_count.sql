SELECT
  :owner AS owner,
  COUNT(DISTINCT repo.id) AS repo_count
FROM repos repo
JOIN runs run ON run.repo_id = repo.id
WHERE repo.owner = :owner;
