# CSV Download Functionality — Design Spec

**Issue**: [#19](https://github.com/DPGAlliance/maturity-tool/issues/19)
**Date**: 2026-06-07
**Scope**: Per-repo snapshot CSV downloads in the Streamlit data viewer

## Summary

Add CSV download buttons to the Streamlit data viewer so users can export the raw data they are already viewing. Each data section (branches, commits, releases, issues, PRs) gets its own download button placed next to its existing "View Raw Data" expander. An additional "metrics snapshot" CSV captures the computed analyzer values for the currently selected repo.

## Architecture

No new services, dependencies, or database changes. The feature uses Streamlit's built-in `st.download_button` widget and pandas `DataFrame.to_csv()`.

### Data sections and CSV schemas

| Section | Source DataFrame | Key columns |
|---------|-----------------|-------------|
| Branches | `branches_df` | branch_name, last_commit_date, total_commits |
| Commits | `commits_full_df` | oid, authored_date, author_login, additions, deletions, message |
| Releases | `release_analyzer.df_releases` | tag_name, name, created_at, total_downloads |
| Issues | `issue_analyzer.df_issues` | github_id, state, author_login, created_at, closed_at, labels |
| PRs | `issue_analyzer.df_prs` | github_id, state, author_login, created_at, merged_at, closed_at, labels |
| Metrics | Computed from analyzers | metric_name, metric_value (flat key-value pairs) |

### UI placement

Each download button sits inside the existing raw-data expander or just below the section header. The filename follows the pattern `{owner}_{repo}_{section}.csv` (e.g., `mosip_commons_commits.csv`).

The metrics snapshot button goes at the top of the page (after repo info) since it summarizes the whole repo.

### Implementation approach

1. Add a helper function `csv_download_button(df, owner, repo, section_name)` in `ui.py` that wraps `st.download_button` with consistent naming and styling.
2. Call this helper in each display function after showing the data.
3. Add a `collect_metrics_snapshot()` function that gathers computed metrics from analyzers into a flat DataFrame.
4. Place a metrics CSV download button near the repo info section.

### What this does NOT include

- Multi-repo / org-level CSV export (future work)
- Historical metrics over time (future work)
- API CSV endpoint (future work)
- Excel/ZIP bundling (future work)

## Testing

- Manual: select a repo in the viewer, verify each download button produces a valid CSV with correct data
- Edge cases: repo with no releases, repo with no issues/PRs, empty commits
