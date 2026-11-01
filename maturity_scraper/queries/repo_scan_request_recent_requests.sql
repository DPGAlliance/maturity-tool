SELECT
  requested_at,
  source_endpoint,
  repo_url_raw,
  normalized_host,
  provider_family,
  provider_detected,
  repo_path,
  valid,
  accessible,
  scan_supported,
  confidence,
  result_class,
  created_scan_job_id,
  error_message
FROM repo_scan_request_logs
ORDER BY requested_at DESC
LIMIT 100;
