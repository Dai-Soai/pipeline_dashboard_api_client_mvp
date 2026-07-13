"""Tests for the CLI health command handler."""

from dataclasses import dataclass
from io import StringIO

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    DashboardApiClientError,
    DashboardClient,
    ErrorKind,
    HttpMethod,
    ResponseParser,
)
from pipeline_dashboard_api_client.cli.commands.health import (
    run_health_command,
)
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
)


class RecordingTransport:
    """Transport double used by health command tests."""

    def __init__(
        self,
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
        """Record and execute a fake request."""
        self.requests.append(request)

        if self.error is not None:
            raise self.error

        if self.response is None:
            raise AssertionError("response is not configured")

        return self.response

    def close(self) -> None:
        """Satisfy the dashboard transport protocol."""


@dataclass(slots=True)
class CommandDependencies:
    """Health command dependency fixture."""

    client: DashboardClient
    response_parser: ResponseParser


def build_response(
    content: bytes,
) -> ApiResponse[bytes]:
    """Build a reusable raw health response."""
    return ApiResponse(
        status_code=200,
        data=content,
        headers={"content-type": "application/json"},
        request_id="request-health-31",
        elapsed_ms=1.0,
    )


def build_dependencies(
    transport: RecordingTransport,
) -> CommandDependencies:
    """Build health command dependencies."""
    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
    )

    return CommandDependencies(
        client=DashboardClient(
            config,
            transport=transport,
        ),
        response_parser=ResponseParser(),
    )


def test_health_command_fetches_health_endpoint() -> None:
    """Health command requests GET /health."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_health_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert len(transport.requests) == 1
    assert transport.requests[0].method is HttpMethod.GET
    assert transport.requests[0].path == "/health"


def test_health_command_prints_complete_payload() -> None:
    """Health output preserves the complete backend document."""
    transport = RecordingTransport(
        response=build_response(
            b'{'
            b'"status":"healthy",'
            b'"service":"dashboard-backend",'
            b'"version":"0.1.0"'
            b'}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_health_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        '{"service":"dashboard-backend",'
        '"status":"healthy",'
        '"version":"0.1.0"}\n'
    )


def test_health_command_supports_pretty_output() -> None:
    """Health command supports indented JSON output."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy","service":"dashboard"}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_health_command(
        dependencies,
        output_mode=OutputMode.PRETTY,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue().startswith("{\n")
    assert '  "status": "healthy"' in output.getvalue()


def test_health_command_prints_transport_error() -> None:
    """Transport failures become structured stderr output."""
    error = DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.CONNECTION,
            message="dashboard API connection failed",
        )
    )
    transport = RecordingTransport(error=error)
    dependencies = build_dependencies(transport)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_health_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"connection"' in error_output.getvalue()


def test_health_command_prints_validation_error() -> None:
    """Missing health status becomes a structured validation error."""
    transport = RecordingTransport(
        response=build_response(b'{"service":"dashboard"}')
    )
    dependencies = build_dependencies(transport)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_health_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"validation"' in error_output.getvalue()
    assert '"field":"status"' in error_output.getvalue()
