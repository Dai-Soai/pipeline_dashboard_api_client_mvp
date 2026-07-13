"""Integration tests for the modular CLI main dispatcher."""

from __future__ import annotations

from collections.abc import Callable
from io import StringIO

import httpx
import pytest

from pipeline_dashboard_api_client import (
    ApiRequest,
    ApiResponse,
    DashboardClient,
    HttpTransport,
    ResponseParser,
)
from pipeline_dashboard_api_client.cli.config import CliRuntimeConfig
from pipeline_dashboard_api_client.cli.factory import CliDependencies
from pipeline_dashboard_api_client.cli.main import main


class MockHttpTransport(HttpTransport):
    """HTTP transport backed by a deterministic mock response."""

    def __init__(
        self,
        runtime_config: CliRuntimeConfig,
        *,
        response_content: bytes,
        status_code: int = 200,
    ) -> None:
        """Initialize a mock HTTP transport."""
        self.requests: list[ApiRequest] = []

        def handler(
            request: httpx.Request,
        ) -> httpx.Response:
            return httpx.Response(
                status_code=status_code,
                content=response_content,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": "request-main-31",
                },
            )

        self._mock_client = httpx.Client(
            transport=httpx.MockTransport(handler)
        )

        super().__init__(
            runtime_config.client,
            client=self._mock_client,
        )

    def execute(
        self,
        request: ApiRequest,
    ) -> ApiResponse[bytes]:
        """Record and execute the normalized request."""
        self.requests.append(request)
        return super().execute(request)

    def close(self) -> None:
        """Close transport state and its externally injected mock client."""
        if self.is_closed:
            return

        super().close()
        self._mock_client.close()


def build_dependency_builder(
    *,
    response_content: bytes,
    transports: list[MockHttpTransport],
) -> Callable[[CliRuntimeConfig], CliDependencies]:
    """Build a dependency factory backed by a mock HTTP response."""

    def builder(
        runtime_config: CliRuntimeConfig,
    ) -> CliDependencies:
        transport = MockHttpTransport(
            runtime_config,
            response_content=response_content,
        )
        transports.append(transport)

        client = DashboardClient(
            runtime_config.client,
            transport=transport,
        )

        return CliDependencies(
            client=client,
            response_parser=ResponseParser(),
            transport=transport,
        )

    return builder


def test_main_version_prints_version_without_dependencies() -> None:
    """Version command does not construct API dependencies."""
    output = StringIO()
    called = False

    def forbidden_builder(
        runtime_config: CliRuntimeConfig,
    ) -> CliDependencies:
        nonlocal called
        called = True
        raise AssertionError(
            f"unexpected runtime config: {runtime_config}"
        )

    exit_code = main(
        ["version"],
        dependency_builder=forbidden_builder,
        output_stream=output,
    )

    assert exit_code == 0
    assert output.getvalue() == "0.1.0\n"
    assert called is False


def test_main_dispatches_dashboard_command() -> None:
    """Dashboard command executes GET /dashboard."""
    transports: list[MockHttpTransport] = []
    output = StringIO()

    exit_code = main(
        [
            "dashboard",
            "--base-url",
            "https://dashboard.example.com",
            "--compact",
        ],
        dependency_builder=build_dependency_builder(
            response_content=(
                b'{"status":"healthy","panels":[]}'
            ),
            transports=transports,
        ),
        output_stream=output,
    )

    assert exit_code == 0
    assert output.getvalue() == (
        '{"panels":[],"status":"healthy"}\n'
    )
    assert len(transports) == 1
    assert transports[0].requests[0].path == "/dashboard"
    assert transports[0].is_closed is True


def test_main_dispatches_summary_command() -> None:
    """Summary command executes GET /summary."""
    transports: list[MockHttpTransport] = []
    output = StringIO()

    exit_code = main(
        ["summary", "--compact"],
        dependency_builder=build_dependency_builder(
            response_content=(
                b'{"overall_status":"healthy","source_count":4}'
            ),
            transports=transports,
        ),
        output_stream=output,
    )

    assert exit_code == 0
    assert output.getvalue() == (
        '{"overall_status":"healthy","source_count":4}\n'
    )
    assert transports[0].requests[0].path == "/summary"


def test_main_dispatches_health_command() -> None:
    """Health command executes GET /health."""
    transports: list[MockHttpTransport] = []
    output = StringIO()

    exit_code = main(
        ["health", "--compact"],
        dependency_builder=build_dependency_builder(
            response_content=(
                b'{"status":"healthy","service":"dashboard"}'
            ),
            transports=transports,
        ),
        output_stream=output,
    )

    assert exit_code == 0
    assert output.getvalue() == (
        '{"service":"dashboard","status":"healthy"}\n'
    )
    assert transports[0].requests[0].path == "/health"


def test_main_dispatches_validate_command() -> None:
    """Validate command checks the health endpoint."""
    transports: list[MockHttpTransport] = []
    output = StringIO()
    error_output = StringIO()

    exit_code = main(
        ["validate"],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":"healthy"}',
            transports=transports,
        ),
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == 0
    assert output.getvalue() == (
        "Dashboard backend reachable.\n"
    )
    assert error_output.getvalue() == ""
    assert transports[0].requests[0].path == "/health"


def test_main_forwards_connection_configuration() -> None:
    """Parsed CLI settings are passed into dependency configuration."""
    captured_configs: list[CliRuntimeConfig] = []
    transports: list[MockHttpTransport] = []

    def builder(
        runtime_config: CliRuntimeConfig,
    ) -> CliDependencies:
        captured_configs.append(runtime_config)

        return build_dependency_builder(
            response_content=b'{"status":"healthy"}',
            transports=transports,
        )(runtime_config)

    exit_code = main(
        [
            "health",
            "--base-url",
            "https://custom.example.com/",
            "--timeout",
            "3.5",
            "--retry",
            "5",
            "--header",
            "Authorization=Bearer test",
            "--compact",
        ],
        dependency_builder=builder,
        output_stream=StringIO(),
    )

    assert exit_code == 0
    assert len(captured_configs) == 1

    config = captured_configs[0].client

    assert config.base_url == "https://custom.example.com"
    assert config.timeout_seconds == 3.5
    assert config.max_retries == 5
    assert config.default_headers == {
        "Authorization": "Bearer test"
    }


def test_main_reports_invalid_header_configuration() -> None:
    """Malformed headers produce a usage error without dependencies."""
    output = StringIO()
    error_output = StringIO()
    called = False

    def forbidden_builder(
        runtime_config: CliRuntimeConfig,
    ) -> CliDependencies:
        nonlocal called
        called = True
        raise AssertionError(
            f"unexpected runtime config: {runtime_config}"
        )

    exit_code = main(
        [
            "dashboard",
            "--header",
            "Authorization",
        ],
        dependency_builder=forbidden_builder,
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == 2
    assert output.getvalue() == ""
    assert "Configuration error:" in error_output.getvalue()
    assert "NAME=VALUE" in error_output.getvalue()
    assert called is False


def test_main_validate_returns_failure_for_unhealthy_backend() -> None:
    """Validate propagates unhealthy backend status as exit code one."""
    transports: list[MockHttpTransport] = []
    output = StringIO()
    error_output = StringIO()

    exit_code = main(
        ["validate"],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":"degraded"}',
            transports=transports,
        ),
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == 1
    assert output.getvalue() == ""
    assert error_output.getvalue() == (
        "Dashboard backend returned an unhealthy status.\n"
    )


def test_main_returns_failure_for_invalid_json() -> None:
    """Parser failures propagate through the main dispatcher."""
    transports: list[MockHttpTransport] = []
    output = StringIO()
    error_output = StringIO()

    exit_code = main(
        ["dashboard", "--compact"],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":',
            transports=transports,
        ),
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == 1
    assert output.getvalue() == ""
    assert '"kind":"decoding"' in error_output.getvalue()
    assert transports[0].is_closed is True


@pytest.mark.parametrize(
    ("command", "expected_path"),
    [
        ("dashboard", "/dashboard"),
        ("summary", "/summary"),
        ("health", "/health"),
        ("validate", "/health"),
    ],
)
def test_main_closes_dependencies_after_each_command(
    command: str,
    expected_path: str,
) -> None:
    """Every API command closes its dependency bundle."""
    transports: list[MockHttpTransport] = []

    exit_code = main(
        [command, "--compact"],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":"healthy"}',
            transports=transports,
        ),
        output_stream=StringIO(),
        error_stream=StringIO(),
    )

    assert exit_code == 0
    assert transports[0].requests[0].path == expected_path
    assert transports[0].is_closed is True
