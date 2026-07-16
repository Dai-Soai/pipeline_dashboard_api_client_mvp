"""Tests for JSON export contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExporter,
    JsonExportError,
    JsonExportErrorKind,
    JsonExportRequest,
    JsonExportResult,
)
from pipeline_dashboard_api_client.parser import JsonValue


class CompatibleExporter:
    """Minimal object satisfying the JSON exporter protocol."""

    def export(
        self,
        value: JsonValue,
        request: JsonExportRequest,
    ) -> JsonExportResult:
        """Return a deterministic export result."""
        del value

        return JsonExportResult(
            path=request.path,
            bytes_written=12,
            overwritten=request.overwrite,
        )


class IncompatibleExporter:
    """Object that does not satisfy the JSON exporter protocol."""


def test_export_request_uses_pretty_mode_by_default() -> None:
    """Export requests default to pretty JSON without overwriting."""
    request = JsonExportRequest(
        path=Path("dashboard.json"),
    )

    assert request.path == Path("dashboard.json")
    assert request.output_mode is OutputMode.PRETTY
    assert request.overwrite is False


def test_export_request_preserves_explicit_options() -> None:
    """Export requests retain explicit output and overwrite options."""
    request = JsonExportRequest(
        path=Path("summary.json"),
        output_mode=OutputMode.COMPACT,
        overwrite=True,
    )

    assert request.path == Path("summary.json")
    assert request.output_mode is OutputMode.COMPACT
    assert request.overwrite is True


def test_export_result_preserves_success_metadata() -> None:
    """Successful export results retain normalized metadata."""
    result = JsonExportResult(
        path=Path("health.json"),
        bytes_written=128,
        overwritten=False,
    )

    assert result.path == Path("health.json")
    assert result.bytes_written == 128
    assert result.overwritten is False


@pytest.mark.parametrize(
    "invalid_bytes_written",
    [
        -1,
        True,
    ],
)
def test_export_result_rejects_invalid_byte_counts(
    invalid_bytes_written: int,
) -> None:
    """Export results reject negative and boolean byte counts."""
    with pytest.raises(
        ValueError,
        match="bytes_written must be a non-negative integer",
    ):
        JsonExportResult(
            path=Path("dashboard.json"),
            bytes_written=invalid_bytes_written,
            overwritten=False,
        )


def test_export_error_exposes_normalized_context() -> None:
    """Export failures expose their kind, path, and message."""
    error = JsonExportError(
        kind=JsonExportErrorKind.WRITE_FAILED,
        path=Path("dashboard.json"),
        message="  controlled write failure  ",
    )

    assert error.kind is JsonExportErrorKind.WRITE_FAILED
    assert error.path == Path("dashboard.json")
    assert str(error) == "controlled write failure"


def test_export_error_rejects_empty_messages() -> None:
    """Export failures require a meaningful diagnostic message."""
    with pytest.raises(
        ValueError,
        match="export error message must not be empty",
    ):
        JsonExportError(
            kind=JsonExportErrorKind.INVALID_PATH,
            path=Path("dashboard.json"),
            message="   ",
        )


def test_compatible_exporter_satisfies_protocol() -> None:
    """Structurally compatible exporters satisfy JsonExporter."""
    exporter = CompatibleExporter()

    assert isinstance(exporter, JsonExporter)


def test_incompatible_exporter_does_not_satisfy_protocol() -> None:
    """Objects without an export method fail protocol inspection."""
    exporter = IncompatibleExporter()

    assert not isinstance(exporter, JsonExporter)
