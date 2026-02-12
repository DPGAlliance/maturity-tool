# Maturity Tool Docs

These docs cover the new storage/cache layer and scheduled refresh workflows.

## Quick Start
- Set env vars in `.env` (see `.env.template`). The app auto-loads `.env`.
- Optional DB cache switch in the Streamlit app: `USE_DB_CACHE=true`.
- Refresh cache + metrics snapshots: `python scripts/refresh_cache.py --owner <org>`.

## What Is Documented Here
- Storage module layout and behavior.
- Cache policy and metrics snapshots.
- Refresh script options.
- API endpoints and auth.
- Planned changes to the storage layer.

## What Is Not Documented Yet
We will add docs for `maturity_tools` and `data_viewer` later after refactors.
