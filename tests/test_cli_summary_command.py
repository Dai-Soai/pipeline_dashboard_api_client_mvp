"""Tests for the CLI summary command handler."""

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
from pipeline_dashboard_api_client.cli.commands.summary import (
    run_summary_command,
)
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
)


class RecordingTransport:
    """Transport double used by summary command tests."""

    def __init__(
        self,
        response: ApiResponse[bytes] | None = None,
        error: DashboardApiClientError | None = None,
    ) -> None:
        """Initialize the transport double."""
        self.response = response
        self.error = error
        self.requests: list[ApiRequest] = []
        self.close_calls = 0

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
        """Record close calls."""
        self.close_calls += 1


@dataclass(slots=True)
class CommandDependencies:
    """Summary command dependency fixture."""

    client: DashboardClient
    response_parser: ResponseParser


def build_response(
    content: bytes,
) -> ApiResponse[bytes]:
    """Build a reusable raw summary response."""
    return ApiResponse(
        status_code=200,
        data=content,
        headers={"content-type": "application/json"},
        request_id="request-summary-31",
        elapsed_ms=1.75,
    )


def build_dependencies(
    transport: RecordingTransport,
) -> CommandDependencies:
    """Build summary command dependencies."""
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


def test_summary_command_fetches_summary_endpoint() -> None:
    """Summary command requests GET /summary."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy","total_panels":3}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert len(transport.requests) == 1
    assert transport.requests[0].method is HttpMethod.GET
    assert transport.requests[0].path == "/summary"


def test_summary_command_prints_compact_json() -> None:
    """Compact mode emits one-line summary JSON."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":"healthy","source_count":4}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        '{"overall_status":"healthy","source_count":4}\n'
    )


def test_summary_command_prints_pretty_json() -> None:
    """Pretty mode emits indented summary JSON."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"ok","overall_status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.PRETTY,
        output_stream=output,
    )

    rendered = output.getvalue()

    assert exit_code == EXIT_SUCCESS
    assert rendered.startswith("{\n")
    assert '  "overall_status": "healthy"' in rendered
    assert '  "status": "ok"' in rendered
    assert rendered.endswith("}\n")


def test_summary_command_preserves_complete_payload() -> None:
    """The command prints the complete summary document."""
    transport = RecordingTransport(
        response=build_response(
            b'{'
            b'"status":"warning",'
            b'"overall_status":"degraded",'
            b'"generated_at":"2026-07-13T22:00:00Z",'
            b'"metrics":{"healthy":8,"warning":2}'
            b'}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        '{"generated_at":"2026-07-13T22:00:00Z",'
        '"metrics":{"healthy":8,"warning":2},'
        '"overall_status":"degraded",'
        '"status":"warning"}\n'
    )


def test_summary_command_prints_transport_error() -> None:
    """Transport failures are printed as structured JSON errors."""
    error = DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.TIMEOUT,
            message="dashboard API request timed out",
            details={
                "attempts": 3,
            },
        )
    )
    transport = RecordingTransport(error=error)
    dependencies = build_dependencies(transport)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert error_output.getvalue() == (
        '{"error":{"details":{"attempts":3},'
        '"kind":"timeout",'
        '"message":"dashboard API request timed out"}}\n'
    )


def test_summary_command_prints_parser_error() -> None:
    """Malformed summary JSON becomes a structured CLI error."""
    transport = RecordingTransport(
        response=build_response(
            b'{"overall_status":'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"decoding"' in error_output.getvalue()
    assert (
        '"message":"dashboard API response is not valid JSON"'
        in error_output.getvalue()
    )
    assert '"request_id":"request-summary-31"' in (
        error_output.getvalue()
    )


def test_summary_command_does_not_close_dependencies() -> None:
    """Resource lifecycle remains owned by the caller."""
    transport = RecordingTransport(
        response=build_response(
            b'{"status":"healthy"}'
        )
    )
    dependencies = build_dependencies(transport)
    output = StringIO()

    run_summary_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
    )

    assert dependencies.client.is_closed is False
    assert transport.close_calls == 0
