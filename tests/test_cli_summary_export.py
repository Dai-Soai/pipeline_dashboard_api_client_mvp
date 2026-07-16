"""Tests for summary JSON export integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    DashboardApiClientError,
    DashboardClient,
    ErrorKind,
    ResponseParser,
)
from pipeline_dashboard_api_client.cli.commands.summary import (
    run_summary_command,
)
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.export_contracts import (
    JsonExportError,
    JsonExportErrorKind,
    JsonExportRequest,
    JsonExportResult,
)
from pipeline_dashboard_api_client.cli.json_exporter import (
    AtomicJsonFileExporter,
)
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
)
from pipeline_dashboard_api_client.parser import JsonValue


class RecordingTransport:
    """Transport double used by summary export tests."""

    def __init__(
        self,
        *,
        response: ApiResponse[bytes] | None = None,
        error: DashboardApiClientError | None = None,
    ) -> None:
        """Initialize the transport double."""
        self.response = response
        self.error = error
        self.requests: list[ApiRequest] = []

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Record and execute one fake request."""
        self.requests.append(request)

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("response is not configured")

        return self.response

    def close(self) -> None:
        """Close the fake transport."""


@dataclass(slots=True)
class CommandDependencies:
    """Summary command dependency fixture."""

    client: DashboardClient
    response_parser: ResponseParser


class RecordingExporter:
    """Exporter double recording export calls."""

    def __init__(self) -> None:
        """Initialize empty export history."""
        self.calls: list[
            tuple[JsonValue, JsonExportRequest]
        ] = []

    def export(
        self,
        value: JsonValue,
        request: JsonExportRequest,
    ) -> JsonExportResult:
        """Record one export and return deterministic metadata."""
        self.calls.append(
            (
                value,
                request,
            )
        )

        return JsonExportResult(
            path=request.path,
            bytes_written=31,
            overwritten=request.overwrite,
        )


class FailingExporter:
    """Exporter double raising one normalized failure."""

    def __init__(
        self,
        error: JsonExportError,
    ) -> None:
        """Initialize the failing exporter."""
        self.error = error
        self.calls = 0

    def export(
        self,
        value: JsonValue,
        request: JsonExportRequest,
    ) -> JsonExportResult:
        """Raise the configured export failure."""
        del value
        del request

        self.calls += 1
        raise self.error


def build_response(
    content: bytes,
) -> ApiResponse[bytes]:
    """Build a reusable raw summary response."""
    return ApiResponse(
        status_code=200,
        data=content,
        headers={
            "content-type": "application/json",
        },
        request_id="request-summary-export-31",
        elapsed_ms=1.75,
    )


def build_dependencies(
    transport: RecordingTransport,
) -> CommandDependencies:
    """Build summary export command dependencies."""
    return CommandDependencies(
        client=DashboardClient(
            ApiClientConfig(
                base_url="https://dashboard.example.com",
            ),
            transport=transport,
        ),
        response_parser=ResponseParser(),
    )


def test_summary_export_calls_exporter_with_complete_payload(
    tmp_path: Path,
) -> None:
    """Summary export passes the complete parsed payload."""
    transport = RecordingTransport(
        response=build_response(
            b'{'
            b'"status":"warning",'
            b'"overall_status":"degraded",'
            b'"generated_at":"2026-07-16T18:45:00Z",'
            b'"metrics":{"healthy":8,"warning":2}'
            b'}'
        )
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    request = JsonExportRequest(
        path=tmp_path / "summary.json",
        output_mode=OutputMode.COMPACT,
    )
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=request,
        exporter=exporter,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == ""
    assert len(exporter.calls) == 1

    value, recorded_request = exporter.calls[0]

    assert value == {
        "status": "warning",
        "overall_status": "degraded",
        "generated_at": "2026-07-16T18:45:00Z",
        "metrics": {
            "healthy": 8,
            "warning": 2,
        },
    }
    assert recorded_request is request


def test_summary_export_writes_atomic_json_file(
    tmp_path: Path,
) -> None:
    """Summary command integrates with the atomic file exporter."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":"healthy","source_count":4}'
        )
    )
    dependencies = build_dependencies(transport)
    destination = tmp_path / "summary.json"
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
            output_mode=OutputMode.COMPACT,
        ),
        exporter=AtomicJsonFileExporter(),
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == ""
    assert destination.read_text(
        encoding="utf-8",
    ) == (
        '{"overall_status":"healthy","source_count":4}\n'
    )


def test_summary_export_requires_exporter(
    tmp_path: Path,
) -> None:
    """An export request without an exporter fails clearly."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()
    error_output = StringIO()
    destination = tmp_path / "summary.json"

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
        ),
        output_stream=output,
        error_stream=error_output,
    )

    payload = json.loads(
        error_output.getvalue()
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert payload == {
        "error": {
            "kind": "exporter_missing",
            "message": (
                "JSON exporter is required when an export "
                "request is provided"
            ),
            "path": str(destination),
        }
    }


def test_summary_export_normalizes_export_failure(
    tmp_path: Path,
) -> None:
    """Filesystem export failures become structured CLI errors."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    destination = tmp_path / "summary.json"
    error = JsonExportError(
        kind=JsonExportErrorKind.WRITE_FAILED,
        path=destination,
        message="controlled summary export failure",
    )
    exporter = FailingExporter(error)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
        ),
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    payload = json.loads(
        error_output.getvalue()
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert exporter.calls == 1
    assert payload == {
        "error": {
            "kind": "write_failed",
            "message": "controlled summary export failure",
            "path": str(destination),
        }
    }


def test_summary_api_failure_does_not_call_exporter(
    tmp_path: Path,
) -> None:
    """API failures terminate before the export path is reached."""
    api_error = DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.TIMEOUT,
            message="controlled summary timeout",
        )
    )
    transport = RecordingTransport(
        error=api_error,
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    output = StringIO()
    error_output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=tmp_path / "summary.json",
        ),
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert exporter.calls == []
    assert '"kind":"timeout"' in (
        error_output.getvalue()
    )


def test_summary_export_does_not_close_dependencies(
    tmp_path: Path,
) -> None:
    """Summary export does not take ownership of client lifecycle."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)

    run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=tmp_path / "summary.json",
        ),
        exporter=AtomicJsonFileExporter(),
    )

    assert dependencies.client.is_closed is False
