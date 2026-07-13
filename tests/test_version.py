"""Tests for package version metadata."""

from pipeline_dashboard_api_client import __version__


def test_version() -> None:
    """The package exposes its initial semantic version."""
    assert __version__ == "0.1.0"
