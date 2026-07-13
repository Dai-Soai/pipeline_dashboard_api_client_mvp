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

```bash
radar-dashboard-client version
Development setup
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Quality checks
ruff check .
mypy src tests
pytest

