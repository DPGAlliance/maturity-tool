# DPG Maturity Tool Workspace

This repository contains two independently deployable projects:

- [`maturity_scraper/`](maturity_scraper/): the existing maturity-data collection,
  API, viewer, and scheduler stack.
- [`evidenceAI/`](evidenceAI/): the future evidence collection and validation
  service for nomination and maturity-assessment workflows.

Each project has its own documentation and Docker Compose configuration. Shared
Git history is maintained at this workspace root; services exchange data only
through explicit APIs.
