SELECT
  COALESCE(provider_family, 'unknown') AS provider_family,
  COALESCE(provider_detected, 'unknown') AS provider_detected,
  COUNT(*) AS request_count,
  COUNT(*) FILTER (WHERE source_endpoint = 'validate') AS validate_count,
  COUNT(*) FILTER (WHERE source_endpoint = 'create_scan') AS create_count,
  COUNT(*) FILTER (WHERE valid) AS valid_count,
  COUNT(*) FILTER (WHERE accessible) AS accessible_count,
  COUNT(*) FILTER (WHERE scan_supported) AS supported_count
FROM repo_scan_request_logs
GROUP BY provider_family, provider_detected
ORDER BY request_count DESC, provider_family, provider_detected;
