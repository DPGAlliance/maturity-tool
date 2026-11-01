SELECT
  source_endpoint,
  result_class,
  COUNT(*) AS request_count
FROM repo_scan_request_logs
GROUP BY source_endpoint, result_class
ORDER BY request_count DESC, source_endpoint, result_class;
