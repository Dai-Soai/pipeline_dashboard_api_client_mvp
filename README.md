# Pipeline Dashboard API Client MVP

Utility #31 of RADAR_SERVICE.

A typed Python API client for communicating with the Pipeline Dashboard
Backend produced by Utility #30.

## Current phase

M1 — Bootstrap

## Initial capabilities

- Python package bootstrap
- Semantic version module
- Console entry point
- `version` command
- Ruff configuration
- Mypy strict configuration
- Pytest bootstrap tests

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
~~~

## Development setup

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

## Quality checks

ruff check .
mypy src tests
pytest

