"""Tests for validation result JSON export behavior."""

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
from pipeline_dashboard_api_client.cli.commands.validate import (
    run_validate_command,
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
    """Transport double used by validation export tests."""

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
    """Validation command dependency fixture."""

    client: DashboardClient
    response_parser: ResponseParser


class RecordingExporter:
    """Exporter double recording validation result exports."""

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
            bytes_written=48,
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
    """Build a reusable raw health response."""
    return ApiResponse(
        status_code=200,
        data=content,
        headers={
            "content-type": "application/json",
        },
        request_id="request-validate-export-31",
        elapsed_ms=1.25,
    )


def build_dependencies(
    transport: RecordingTransport,
) -> CommandDependencies:
    """Build validation export command dependencies."""
    return CommandDependencies(
        client=DashboardClient(
            ApiClientConfig(
                base_url="https://dashboard.example.com",
            ),
            transport=transport,
        ),
        response_parser=ResponseParser(),
    )


def test_validate_export_emits_normalized_validation_result(
    tmp_path: Path,
) -> None:
    """Healthy validation exports its normalized result document."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"HEALTHY","service":"dashboard"}'
        )
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    request = JsonExportRequest(
        path=tmp_path / "validation.json",
        output_mode=OutputMode.COMPACT,
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=request,
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == ""
    assert error_output.getvalue() == ""
    assert len(exporter.calls) == 1

    value, recorded_request = exporter.calls[0]

    assert value == {
        "message": "Dashboard backend reachable.",
        "valid": True,
    }
    assert recorded_request is request


def test_validate_export_writes_atomic_json_file(
    tmp_path: Path,
) -> None:
    """Validation integrates with the atomic JSON file exporter."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"ok"}'
        )
    )
    dependencies = build_dependencies(transport)
    destination = tmp_path / "validation.json"
    output = StringIO()

    exit_code = run_validate_command(
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
        '{"message":"Dashboard backend reachable.",'
        '"valid":true}\n'
    )


def test_validate_export_requires_exporter(
    tmp_path: Path,
) -> None:
    """An export request without an exporter fails clearly."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    destination = tmp_path / "validation.json"
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
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


def test_validate_export_normalizes_filesystem_failure(
    tmp_path: Path,
) -> None:
    """Export failures become structured CLI errors."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    destination = tmp_path / "validation.json"
    exporter = FailingExporter(
        JsonExportError(
            kind=JsonExportErrorKind.WRITE_FAILED,
            path=destination,
            message="controlled validation export failure",
        )
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
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
            "message": "controlled validation export failure",
            "path": str(destination),
        }
    }


def test_unhealthy_validation_does_not_export_result(
    tmp_path: Path,
) -> None:
    """Unhealthy validation terminates before export."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"degraded"}'
        )
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    destination = tmp_path / "validation.json"
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
        ),
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert error_output.getvalue() == (
        "Dashboard backend returned an unhealthy status.\n"
    )
    assert exporter.calls == []
    assert destination.exists() is False


def test_validate_api_failure_does_not_export_error(
    tmp_path: Path,
) -> None:
    """API failures remain on stderr and do not create export files."""
    transport = RecordingTransport(
        error=DashboardApiClientError(
            ApiErrorPayload(
                kind=ErrorKind.TIMEOUT,
                message="controlled validation timeout",
            )
        )
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    destination = tmp_path / "validation.json"
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
        ),
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"timeout"' in error_output.getvalue()
    assert exporter.calls == []
    assert destination.exists() is False


def test_validate_parser_failure_does_not_export_error(
    tmp_path: Path,
) -> None:
    """Parser failures remain on stderr and do not create export files."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":'
        )
    )
    dependencies = build_dependencies(transport)
    exporter = RecordingExporter()
    destination = tmp_path / "validation.json"
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=destination,
        ),
        exporter=exporter,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"decoding"' in error_output.getvalue()
    assert exporter.calls == []
    assert destination.exists() is False


def test_validate_export_does_not_close_dependencies(
    tmp_path: Path,
) -> None:
    """Validation export does not own the client lifecycle."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)

    run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        export_request=JsonExportRequest(
            path=tmp_path / "validation.json",
        ),
        exporter=AtomicJsonFileExporter(),
    )

    assert dependencies.client.is_closed is False
