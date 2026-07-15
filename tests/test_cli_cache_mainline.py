"""Integration tests for CLI cache management mainline wiring."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from pipeline_dashboard_api_client.cli.main import main


def test_cache_status_runs_without_network_configuration(
    tmp_path: Path,
) -> None:
    """Cache status does not require backend connection arguments."""
    output = StringIO()
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "cache-status",
            "--cache-dir",
            str(cache_root),
            "--compact",
        ],
        output_stream=output,
    )

    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["cache"]["entry_count"] == 0
    assert payload["cache"]["root"] == str(cache_root)


def test_cache_clear_runs_without_network_configuration(
    tmp_path: Path,
) -> None:
    """Cache clear does not build network dependencies."""
    output = StringIO()
    cache_root = tmp_path / "cache"

    exit_code = main(
        [
            "cache-clear",
            "--cache-dir",
            str(cache_root),
            "--compact",
        ],
        output_stream=output,
    )

    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["cache"]["cleared"] is True
    assert payload["cache"]["deleted_count"] == 0


def test_cache_status_reports_managed_files(
    tmp_path: Path,
) -> None:
    """Mainline cache status reports existing managed entries."""
    output = StringIO()
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    (cache_root / ("a" * 64 + ".json")).write_text(
        "{}",
        encoding="utf-8",
    )
    (cache_root / ("b" * 64 + ".json")).write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "cache-status",
            "--cache-dir",
            str(cache_root),
            "--compact",
        ],
        output_stream=output,
    )

    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["cache"]["entry_count"] == 2


def test_cache_clear_removes_managed_files(
    tmp_path: Path,
) -> None:
    """Mainline cache clear deletes existing managed entries."""
    output = StringIO()
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    first = cache_root / ("a" * 64 + ".json")
    second = cache_root / ("b" * 64 + ".json")

    first.write_text(
        "{}",
        encoding="utf-8",
    )
    second.write_text(
        "{}",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "cache-clear",
            "--cache-dir",
            str(cache_root),
            "--compact",
        ],
        output_stream=output,
    )

    payload = json.loads(output.getvalue())

    assert exit_code == 0
    assert payload["cache"]["deleted_count"] == 2
    assert first.exists() is False
    assert second.exists() is False
