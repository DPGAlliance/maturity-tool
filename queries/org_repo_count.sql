SELECT
  :owner AS owner,
  COUNT(*) AS repo_count
FROM repos
WHERE owner = :owner;
