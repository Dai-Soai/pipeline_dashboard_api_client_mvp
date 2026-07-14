"""Tests for CLI cache management command handlers."""

from io import StringIO
from pathlib import Path

from pipeline_dashboard_api_client.cli.commands.cache import (
    run_cache_clear_command,
    run_cache_status_command,
)
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import EXIT_SUCCESS


class RecordingCacheStore:
    """Cache store double used by command tests."""

    def __init__(
        self,
        root: Path,
        paths: list[Path] | None = None,
    ) -> None:
        """Initialize the store double."""
        self._root = root
        self.paths = [] if paths is None else list(paths)
        self.clear_calls = 0

    @property
    def root(self) -> Path:
        """Return the configured root."""
        return self._root

    def list_paths(self) -> list[Path]:
        """Return configured managed paths."""
        return list(self.paths)

    def clear(self) -> int:
        """Clear paths and return the previous count."""
        self.clear_calls += 1
        deleted_count = len(self.paths)
        self.paths.clear()
        return deleted_count


def test_cache_status_reports_missing_directory(
    tmp_path: Path,
) -> None:
    """Missing cache directories are reported without failure."""
    root = tmp_path / "missing"
    store = RecordingCacheStore(root)
    output = StringIO()

    exit_code = run_cache_status_command(
        store,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        '{"cache":{"entry_count":0,'
        '"exists":false,'
        f'"root":"{root}"}}}}\n'
    )


def test_cache_status_reports_existing_entries(
    tmp_path: Path,
) -> None:
    """Status output reports managed cache entry count."""
    root = tmp_path / "cache"
    root.mkdir()
    store = RecordingCacheStore(
        root,
        paths=[
            root / "first.json",
            root / "second.json",
        ],
    )
    output = StringIO()

    exit_code = run_cache_status_command(
        store,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        '{"cache":{"entry_count":2,'
        '"exists":true,'
        f'"root":"{root}"}}}}\n'
    )


def test_cache_status_supports_pretty_output(
    tmp_path: Path,
) -> None:
    """Cache status supports indented JSON output."""
    store = RecordingCacheStore(tmp_path)
    output = StringIO()

    exit_code = run_cache_status_command(
        store,
        output_mode=OutputMode.PRETTY,
        output_stream=output,
    )

    rendered = output.getvalue()

    assert exit_code == EXIT_SUCCESS
    assert rendered.startswith("{\n")
    assert '"entry_count": 0' in rendered
    assert '"exists": true' in rendered
    assert rendered.endswith("}\n")


def test_cache_clear_deletes_all_entries(
    tmp_path: Path,
) -> None:
    """Cache clear reports how many entries were removed."""
    root = tmp_path / "cache"
    store = RecordingCacheStore(
        root,
        paths=[
            root / "first.json",
            root / "second.json",
            root / "third.json",
        ],
    )
    output = StringIO()

    exit_code = run_cache_clear_command(
        store,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert store.clear_calls == 1
    assert store.paths == []
    assert output.getvalue() == (
        '{"cache":{"cleared":true,'
        '"deleted_count":3,'
        f'"root":"{root}"}}}}\n'
    )


def test_cache_clear_handles_empty_cache(
    tmp_path: Path,
) -> None:
    """Clearing an empty cache remains successful."""
    store = RecordingCacheStore(tmp_path)
    output = StringIO()

    exit_code = run_cache_clear_command(
        store,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert store.clear_calls == 1
    assert '"deleted_count":0' in output.getvalue()


def test_cache_clear_supports_pretty_output(
    tmp_path: Path,
) -> None:
    """Cache clear supports indented JSON output."""
    store = RecordingCacheStore(tmp_path)
    output = StringIO()

    exit_code = run_cache_clear_command(
        store,
        output_mode=OutputMode.PRETTY,
        output_stream=output,
    )

    rendered = output.getvalue()

    assert exit_code == EXIT_SUCCESS
    assert rendered.startswith("{\n")
    assert '"cleared": true' in rendered
    assert '"deleted_count": 0' in rendered
