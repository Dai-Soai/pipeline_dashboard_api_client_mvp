"""Tests for the CLI validate command handler."""

from dataclasses import dataclass
from io import StringIO

import pytest

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
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
)


class RecordingTransport:
    """Transport double used by validation command tests."""

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
        """Execute a fake health request."""
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
    """Validation command dependency fixture."""

    client: DashboardClient
    response_parser: ResponseParser


def build_dependencies(
    *,
    content: bytes | None = None,
    error: DashboardApiClientError | None = None,
) -> CommandDependencies:
    """Build validation command dependencies."""
    response = None

    if content is not None:
        response = ApiResponse(
            status_code=200,
            data=content,
            request_id="request-validate-31",
        )

    transport = RecordingTransport(
        response=response,
        error=error,
    )
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


@pytest.mark.parametrize(
    "status",
    [
        "healthy",
        "HEALTHY",
        "ok",
        "OK",
    ],
)
def test_validate_command_accepts_healthy_status(
    status: str,
) -> None:
    """Healthy and OK statuses produce a successful result."""
    dependencies = build_dependencies(
        content=(
            f'{{"status":"{status}"}}'
        ).encode()
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_SUCCESS
    assert output.getvalue() == (
        "Dashboard backend reachable.\n"
    )
    assert error_output.getvalue() == ""


@pytest.mark.parametrize(
    "status",
    [
        "warning",
        "degraded",
        "unhealthy",
    ],
)
def test_validate_command_rejects_unhealthy_status(
    status: str,
) -> None:
    """Non-healthy backend states return failure."""
    dependencies = build_dependencies(
        content=(
            f'{{"status":"{status}"}}'
        ).encode()
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert error_output.getvalue() == (
        "Dashboard backend returned an unhealthy status.\n"
    )


def test_validate_command_prints_client_error() -> None:
    """Transport failures become structured validation errors."""
    error = DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.TIMEOUT,
            message="dashboard API request timed out",
        )
    )
    dependencies = build_dependencies(error=error)
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"timeout"' in error_output.getvalue()


def test_validate_command_prints_parser_error() -> None:
    """Malformed health documents return structured parser errors."""
    dependencies = build_dependencies(
        content=b'{"status":'
    )
    output = StringIO()
    error_output = StringIO()

    exit_code = run_validate_command(
        dependencies,
        output_mode=OutputMode.COMPACT,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == EXIT_FAILURE
    assert output.getvalue() == ""
    assert '"kind":"decoding"' in error_output.getvalue()
