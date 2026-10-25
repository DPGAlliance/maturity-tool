SELECT
  COALESCE(normalized_host, 'unknown') AS normalized_host,
  COUNT(*) AS request_count,
  COUNT(*) FILTER (WHERE valid) AS valid_count,
  COUNT(*) FILTER (WHERE accessible) AS accessible_count,
  COUNT(*) FILTER (WHERE scan_supported) AS supported_count
FROM repo_scan_request_logs
GROUP BY normalized_host
ORDER BY request_count DESC, normalized_host;
