"""Cache management command handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, TextIO

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_SUCCESS,
    print_json,
)
from pipeline_dashboard_api_client.parser import JsonObject


class CacheCommandStore(Protocol):
    """Filesystem operations required by cache management commands."""

    @property
    def root(self) -> Path:
        """Return the configured cache root."""
        ...

    def list_paths(self) -> list[Path]:
        """Return managed cache files."""
        ...

    def clear(self) -> int:
        """Delete all managed cache files."""
        ...


def run_cache_status_command(
    store: CacheCommandStore,
    *,
    output_mode: OutputMode,
    output_stream: TextIO | None = None,
) -> int:
    """Print filesystem cache status."""
    paths = store.list_paths()
    root = store.root

    document: JsonObject = {
        "cache": {
            "root": str(root),
            "exists": root.is_dir(),
            "entry_count": len(paths),
        }
    }

    print_json(
        document,
        output_mode=output_mode,
        stream=output_stream,
    )

    return EXIT_SUCCESS


def run_cache_clear_command(
    store: CacheCommandStore,
    *,
    output_mode: OutputMode,
    output_stream: TextIO | None = None,
) -> int:
    """Clear managed cache files and print the result."""
    deleted_count = store.clear()

    document: JsonObject = {
        "cache": {
            "root": str(store.root),
            "deleted_count": deleted_count,
            "cleared": True,
        }
    }

    print_json(
        document,
        output_mode=output_mode,
        stream=output_stream,
    )

    return EXIT_SUCCESS
