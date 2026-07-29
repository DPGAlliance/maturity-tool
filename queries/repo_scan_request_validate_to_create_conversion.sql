WITH validates AS (
  SELECT canonical_repo_url, COUNT(*) AS validate_count
  FROM repo_scan_request_logs
  WHERE source_endpoint = 'validate'
  GROUP BY canonical_repo_url
),
creates AS (
  SELECT canonical_repo_url, COUNT(*) AS create_count
  FROM repo_scan_request_logs
  WHERE source_endpoint = 'create_scan'
  GROUP BY canonical_repo_url
)
SELECT
  COALESCE(v.canonical_repo_url, c.canonical_repo_url) AS canonical_repo_url,
  COALESCE(v.validate_count, 0) AS validate_count,
  COALESCE(c.create_count, 0) AS create_count
FROM validates v
FULL OUTER JOIN creates c ON c.canonical_repo_url = v.canonical_repo_url
ORDER BY validate_count DESC, create_count DESC, canonical_repo_url;
