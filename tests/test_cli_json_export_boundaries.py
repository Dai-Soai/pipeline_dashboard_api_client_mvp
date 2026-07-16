"""Boundary tests for JSON export paths and filesystem failures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import NoReturn

import pytest

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExportError,
    JsonExportErrorKind,
    JsonExportRequest,
)
from pipeline_dashboard_api_client.cli.json_exporter import (
    AtomicJsonFileExporter,
)


def test_export_rejects_current_directory_destination(
    tmp_path: Path,
) -> None:
    """A directory-like destination is rejected before writing."""
    exporter = AtomicJsonFileExporter()

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=tmp_path,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.INVALID_PATH
    assert captured.value.path == tmp_path
    assert list(tmp_path.iterdir()) == []


def test_export_rejects_symlink_to_directory(
    tmp_path: Path,
) -> None:
    """A symlink resolving to a directory is not a valid output file."""
    directory = tmp_path / "real-directory"
    directory.mkdir()

    destination = tmp_path / "dashboard.json"
    destination.symlink_to(
        directory,
        target_is_directory=True,
    )

    exporter = AtomicJsonFileExporter()

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=destination,
                overwrite=True,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.INVALID_PATH
    assert captured.value.path == destination
    assert destination.is_symlink() is True
    assert directory.is_dir() is True


def test_no_overwrite_race_preserves_new_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A destination created during publication is never overwritten."""
    destination = tmp_path / "dashboard.json"
    exporter = AtomicJsonFileExporter()

    original_link = os.link

    def create_competing_destination(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        target: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        del source
        del src_dir_fd
        del dst_dir_fd
        del follow_symlinks

        Path(os.fsdecode(target)).write_text(
            "competing writer\n",
            encoding="utf-8",
        )

        raise FileExistsError(
            "controlled destination race"
        )

    monkeypatch.setattr(
        os,
        "link",
        create_competing_destination,
    )

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "exported",
            },
            JsonExportRequest(
                path=destination,
                output_mode=OutputMode.COMPACT,
                overwrite=False,
            ),
        )

    monkeypatch.setattr(
        os,
        "link",
        original_link,
    )

    assert captured.value.kind is JsonExportErrorKind.INVALID_PATH
    assert captured.value.path == destination
    assert destination.read_text(
        encoding="utf-8",
    ) == "competing writer\n"
    assert list(
        tmp_path.glob(".dashboard.json.*.tmp")
    ) == []


def test_temporary_file_creation_failure_is_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Temporary-file creation failures become WRITE_FAILED errors."""
    destination = tmp_path / "dashboard.json"
    exporter = AtomicJsonFileExporter()

    def fail_temporary_file(
        *args: object,
        **kwargs: object,
    ) -> NoReturn:
        del args
        del kwargs
        raise OSError(
            "controlled temporary-file failure"
        )

    monkeypatch.setattr(
        tempfile,
        "NamedTemporaryFile",
        fail_temporary_file,
    )

    with pytest.raises(JsonExportError) as captured:
        exporter.export(
            {
                "status": "ok",
            },
            JsonExportRequest(
                path=destination,
                output_mode=OutputMode.COMPACT,
            ),
        )

    assert captured.value.kind is JsonExportErrorKind.WRITE_FAILED
    assert captured.value.path == destination
    assert destination.exists() is False
    assert list(tmp_path.iterdir()) == []


def test_overwrite_replaces_symlink_without_modifying_target(
    tmp_path: Path,
) -> None:
    """Overwrite replaces the destination symlink, not its target file."""
    target = tmp_path / "original-target.json"
    target.write_text(
        '{"source":"original"}\n',
        encoding="utf-8",
    )

    destination = tmp_path / "dashboard.json"
    destination.symlink_to(target)

    exporter = AtomicJsonFileExporter()

    result = exporter.export(
        {
            "source": "export",
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
            overwrite=True,
        ),
    )

    assert destination.is_symlink() is False
    assert destination.read_text(
        encoding="utf-8",
    ) == '{"source":"export"}\n'

    assert target.read_text(
        encoding="utf-8",
    ) == '{"source":"original"}\n'

    assert result.overwritten is True


def test_unicode_export_reports_utf8_byte_count(
    tmp_path: Path,
) -> None:
    """Unicode exports preserve text and report encoded byte length."""
    destination = tmp_path / "unicode.json"
    exporter = AtomicJsonFileExporter()

    result = exporter.export(
        {
            "message": "Đại Soái - Tri Kỷ",
            "status": "ổn định",
        },
        JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
        ),
    )

    expected = (
        '{"message":"Đại Soái - Tri Kỷ",'
        '"status":"ổn định"}\n'
    )

    assert destination.read_text(
        encoding="utf-8",
    ) == expected

    assert result.bytes_written == len(
        expected.encode("utf-8")
    )

    assert result.bytes_written > len(expected)
