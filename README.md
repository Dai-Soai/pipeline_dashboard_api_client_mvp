# Pipeline Dashboard API Client MVP

Utility #31 of RADAR_SERVICE.

A typed Python API client for communicating with the Pipeline Dashboard
Backend produced by Utility #30.

## Current phase

M9.2 — Metadata and Documentation Corrections

M7 Cache Integration and M8 JSON Export are locked. The project is now in
packaging and release-readiness preparation for version 0.1.0.

## Current capabilities

- Typed Python API client for the Pipeline Dashboard Backend
- Dashboard, summary, health, and connectivity-validation commands
- Configurable backend URL, timeout, retry count, and HTTP headers
- Pretty and compact JSON output modes
- Filesystem response cache with configurable directory and TTL
- Offline stale-cache fallback for eligible connection failures
- Cache status and cache-clear management commands
- Atomic JSON file export for API command results
- Existing-file protection with explicit overwrite control
- Structured API, parser, cache, configuration, and export errors
- Console entry point through `radar-dashboard-client`
- Strict Ruff, mypy, and pytest quality gates

## CLI

Display the installed version:

~~~bash
radar-dashboard-client version
~~~

Fetch the complete dashboard document:

~~~bash
radar-dashboard-client dashboard
~~~

The default backend URL is:

~~~text
http://127.0.0.1:8000
~~~

A custom backend can be supplied explicitly:

~~~bash
radar-dashboard-client dashboard \
  --base-url http://127.0.0.1:8000
~~~

### Cache behavior

API commands use a filesystem cache by default.

Default cache directory:

~~~text
~/.cache/radar-dashboard-client
~~~

Default fresh-cache lifetime:

~~~text
300 seconds
~~~

Use a custom cache directory:

~~~bash
radar-dashboard-client dashboard \
  --cache-dir /tmp/radar-dashboard-cache
~~~

Use a custom cache TTL:

~~~bash
radar-dashboard-client dashboard \
  --cache-ttl 60
~~~

When offline fallback is enabled, stale cache may be returned if the
backend connection fails or times out:

~~~bash
radar-dashboard-client dashboard \
  --offline
~~~

Disable all cache reads and writes:

~~~bash
radar-dashboard-client dashboard \
  --no-cache
~~~

`--offline` and `--no-cache` are mutually exclusive.

### Cache management commands

Display filesystem cache status:

~~~bash
radar-dashboard-client cache-status
~~~

Display compact cache status JSON:

~~~bash
radar-dashboard-client cache-status \
  --compact
~~~

Inspect a custom cache directory:

~~~bash
radar-dashboard-client cache-status \
  --cache-dir /tmp/radar-dashboard-cache
~~~

Delete all managed cache entries:

~~~bash
radar-dashboard-client cache-clear
~~~

Delete entries from a custom cache directory:

~~~bash
radar-dashboard-client cache-clear \
  --cache-dir /tmp/radar-dashboard-cache \
  --compact
~~~

### JSON export

The `dashboard`, `summary`, `health`, and `validate` commands can write
their successful result directly to a JSON file.

Export a compact dashboard document:

~~~bash
radar-dashboard-client dashboard \
  --compact \
  --output-file dashboard.json
~~~

Export a pretty-formatted summary document:

~~~bash
radar-dashboard-client summary \
  --pretty \
  --output-file summary.json
~~~

Export the backend health document:

~~~bash
radar-dashboard-client health \
  --output-file health.json
~~~

Export a normalized validation result:

~~~bash
radar-dashboard-client validate \
  --output-file validation.json
~~~

A successful validation export has this shape:

~~~json
{
  "message": "Dashboard backend reachable.",
  "valid": true
}
~~~

JSON files are published atomically. The destination is not partially
replaced if publication fails.

By default, an existing destination is protected and the command exits
with a failure instead of replacing it.

Use `--overwrite` to replace an existing file explicitly:

~~~bash
radar-dashboard-client health \
  --pretty \
  --output-file health.json \
  --overwrite
~~~

`--overwrite` requires `--output-file`. Supplying `--overwrite` alone is
a CLI configuration error.

When `--output-file` is supplied, the successful result is written to
the destination file and normal result output is suppressed on stdout.

Without `--output-file`, the existing stdout behavior remains unchanged.

API, parser, unhealthy-validation, and export failures are reported on
stderr and do not create a successful result document.

The cache management commands `cache-status` and `cache-clear` do not
accept JSON export options.

### Common API options

The `dashboard`, `summary`, `health`, and `validate` commands support:

~~~text
--base-url URL
--timeout SECONDS
--retry COUNT
--header NAME=VALUE
--pretty
--compact
--cache-dir PATH
--cache-ttl SECONDS
--offline
--no-cache
--output-file PATH
--overwrite
~~~

`--pretty` and `--compact` control both stdout JSON and exported JSON
formatting.

## Development setup

~~~bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
~~~

## Quality checks

~~~bash
ruff check .
mypy src tests
pytest
~~~
