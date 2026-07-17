# Changelog

All notable changes to the Pipeline Dashboard API Client are documented in
this file.

The format follows Keep a Changelog principles, and this project uses Semantic
Versioning.

## [0.1.0] - Unreleased

### Added

- Typed API client for the RADAR_SERVICE Pipeline Dashboard Backend.
- Dashboard, summary, health, and backend validation commands.
- Configurable backend URL, timeout, retry count, and HTTP headers.
- Pretty and compact JSON output modes.
- Filesystem response cache with configurable cache directory and TTL.
- Offline stale-cache fallback for eligible connection and timeout failures.
- Cache status and cache-clear management commands.
- Atomic JSON file export for dashboard, summary, health, and validation
  results.
- Existing-file protection with explicit overwrite support.
- Structured API, parser, cache, configuration, and export errors.
- Console entry point through `radar-dashboard-client`.
- Strict Ruff, mypy, and pytest quality gates.

### Quality

- 383 automated tests passing at the M8 JSON Export lock.
- Ruff validation passing.
- Strict mypy validation passing.

[0.1.0]: https://github.com/Dai-Soai/pipeline_dashboard_api_client_mvp/releases/tag/v0.1.0
