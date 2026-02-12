# Roadmap (Storage Layer)

This is a short-term plan for the storage module only. Docs for other modules
will be added after refactors.

## Planned Changes
- Add a clear data access layer so app code does not touch SQLAlchemy directly.
- Add optional background jobs for scheduled refresh (cron, systemd, or container).
- Decide on a long-term cache location (may move outside this repo).
- Add migrations for schema changes once the model stabilizes.
- Review metrics schema once we finalize the long-term KPIs.
