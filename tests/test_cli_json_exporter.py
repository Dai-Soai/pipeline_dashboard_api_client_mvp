"""Tests for atomic JSON filesystem exports."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExporter,
    JsonExportError,
    JsonExportErrorKind,
    JsonExportRequest,
)
from pipeline_dashboard_api_client.cli.json_exporter import (
    AtomicJsonFileExporter,
)


def test_exporter_satisfies_json_exporter_protocol() -> None:
    """Atomic exporter satisfies the structural exporter contract."""
    exporter = AtomicJsonFileExporter()

    assert isinstance(exporter, JsonExporter)


def test_export_writes_compact_json_with_newline(
    tmp_path: Path,
) -> None:
    """Compact exports use the shared compact JSON renderer."""
    destination = tmp_path / "dashboard.json"
    exporter = AtomicJsonFileExporter()

    result = exporter.export(
        {
            "status": "ok",
            "count": 2,
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
        ),
    )

    expected = '{"count":2,"status":"ok"}\n'

    assert destination.read_text(
        encoding="utf-8",
    ) == expected
    assert result.path == destination
    assert result.bytes_written == len(
        expected.encode("utf-8")
    )
    assert result.overwritten is False


def test_export_writes_pretty_json_with_newline(
    tmp_path: Path,
) -> None:
    """Pretty exports use the shared indented JSON renderer."""
    destination = tmp_path / "summary.json"
    exporter = AtomicJsonFileExporter()

    result = exporter.export(
        {
            "status": "healthy",
            "service": "radar",
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.PRETTY,
        ),
    )

    expected = (
        "{\n"
        '  "service": "radar",\n'
        '  "status": "healthy"\n'
        "}\n"
    )

    assert destination.read_text(
        encoding="utf-8",
    ) == expected
    assert result.bytes_written == len(
        expected.encode("utf-8")
    )
    assert result.overwritten is False


def test_export_creates_missing_parent_directories(
    tmp_path: Path,
) -> None:
    """Atomic exports create missing destination parents."""
    destination = (
        tmp_path
        / "nested"
        / "dashboard"
        / "document.json"
    )
    exporter = AtomicJsonFileExporter()

    exporter.export(
        {
            "status": "ok",
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
        ),
    )

    assert destination.read_text(
        encoding="utf-8",
    ) == '{"status":"ok"}\n'


def test_export_refuses_existing_file_without_overwrite(
    tmp_path: Path,
) -> None:
    """Existing files remain untouched when overwrite is disabled."""
    destination = tmp_path / "dashboard.json"
    destination.write_text(
        "original\n",
        encoding="utf-8",
    )
    exporter = AtomicJsonFileExporter()

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "replacement",
            },
            JsonExportRequest(
                path=destination,
                output_mode=OutputMode.COMPACT,
                overwrite=False,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.INVALID_PATH
    assert captured.value.path == destination
    assert destination.read_text(
        encoding="utf-8",
    ) == "original\n"


def test_export_atomically_overwrites_existing_file(
    tmp_path: Path,
) -> None:
    """Overwrite mode atomically replaces an existing file."""
    destination = tmp_path / "dashboard.json"
    destination.write_text(
        "original\n",
        encoding="utf-8",
    )
    exporter = AtomicJsonFileExporter()

    result = exporter.export(
        {
            "status": "replacement",
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
            overwrite=True,
        ),
    )

    assert destination.read_text(
        encoding="utf-8",
    ) == '{"status":"replacement"}\n'
    assert result.overwritten is True


def test_export_rejects_directory_destination(
    tmp_path: Path,
) -> None:
    """A directory cannot be used as the export file destination."""
    destination = tmp_path / "dashboard.json"
    destination.mkdir()
    exporter = AtomicJsonFileExporter()

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=destination,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.INVALID_PATH
    assert captured.value.path == destination


def test_export_normalizes_parent_creation_failure(
    tmp_path: Path,
) -> None:
    """Invalid parent paths become normalized export failures."""
    parent = tmp_path / "not-a-directory"
    parent.write_text(
        "file\n",
        encoding="utf-8",
    )
    destination = parent / "dashboard.json"
    exporter = AtomicJsonFileExporter()

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=destination,
            ),
        )

    assert (
        captured.value.kind
        is JsonExportErrorKind.PARENT_CREATION_FAILED
    )
    assert captured.value.path == destination


def test_replace_failure_is_normalized_and_temp_file_is_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publication failures do not leave temporary export files."""
    destination = tmp_path / "dashboard.json"
    exporter = AtomicJsonFileExporter()

    def fail_replace(
        *args: object,
    ) -> None:
        del args
        raise OSError("controlled replace failure")

    monkeypatch.setattr(
        os,
        "replace",
        fail_replace,
    )

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=destination,
                output_mode=OutputMode.COMPACT,
                overwrite=True,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.REPLACE_FAILED
    assert captured.value.path == destination
    assert destination.exists() is False
    assert list(
        tmp_path.glob(".dashboard.json.*.tmp")
    ) == []
