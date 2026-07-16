"""Mainline CLI JSON export integration tests."""

from __future__ import annotations

import json
from collections.abc import Callable
from io import StringIO
from pathlib import Path

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
    """HTTP transport backed by a deterministic response."""

    def __init__(
        self,
        runtime_config: CliRuntimeConfig,
        *,
        response_content: bytes,
    ) -> None:
        """Initialize a mock transport."""
        self.requests: list[ApiRequest] = []

        def handler(
            request: httpx.Request,
        ) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                content=response_content,
                headers={
                    "Content-Type": "application/json",
                    "X-Request-ID": "request-export-mainline-31",
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
        """Record and execute a request."""
        self.requests.append(request)
        return super().execute(request)

    def close(self) -> None:
        """Close transport resources."""
        if self.is_closed:
            return

        super().close()
        self._mock_client.close()


def build_dependency_builder(
    *,
    response_content: bytes,
    transports: list[MockHttpTransport],
) -> Callable[[CliRuntimeConfig], CliDependencies]:
    """Build a deterministic dependency factory."""

    def builder(
        runtime_config: CliRuntimeConfig,
    ) -> CliDependencies:
        transport = MockHttpTransport(
            runtime_config,
            response_content=response_content,
        )
        transports.append(transport)

        return CliDependencies(
            client=DashboardClient(
                runtime_config.client,
                transport=transport,
            ),
            response_parser=ResponseParser(),
            transport=transport,
        )

    return builder


@pytest.mark.parametrize(
    (
        "command",
        "response_content",
        "expected_payload",
    ),
    [
        (
            "dashboard",
            b'{"status":"healthy","panels":[]}',
            {
                "panels": [],
                "status": "healthy",
            },
        ),
        (
            "summary",
            b'{"overall_status":"healthy","source_count":4}',
            {
                "overall_status": "healthy",
                "source_count": 4,
            },
        ),
        (
            "health",
            b'{"status":"healthy","service":"dashboard"}',
            {
                "service": "dashboard",
                "status": "healthy",
            },
        ),
        (
            "validate",
            b'{"status":"healthy"}',
            {
                "message": "Dashboard backend reachable.",
                "valid": True,
            },
        ),
    ],
)
def test_main_exports_api_command_result(
    tmp_path: Path,
    command: str,
    response_content: bytes,
    expected_payload: object,
) -> None:
    """Each API command can export through the real mainline."""
    destination = tmp_path / f"{command}.json"
    transports: list[MockHttpTransport] = []
    output = StringIO()
    error_output = StringIO()

    exit_code = main(
        [
            command,
            "--compact",
            "--output-file",
            str(destination),
        ],
        dependency_builder=build_dependency_builder(
            response_content=response_content,
            transports=transports,
        ),
        output_stream=output,
        error_stream=error_output,
    )

    assert exit_code == 0
    assert output.getvalue() == ""
    assert error_output.getvalue() == ""
    assert json.loads(
        destination.read_text(encoding="utf-8")
    ) == expected_payload
    assert transports[0].is_closed is True


def test_main_export_refuses_existing_file_without_overwrite(
    tmp_path: Path,
) -> None:
    """Existing destinations remain untouched by default."""
    destination = tmp_path / "health.json"
    destination.write_text(
        '{"existing":true}\n',
        encoding="utf-8",
    )
    transports: list[MockHttpTransport] = []
    error_output = StringIO()

    exit_code = main(
        [
            "health",
            "--compact",
            "--output-file",
            str(destination),
        ],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":"healthy"}',
            transports=transports,
        ),
        output_stream=StringIO(),
        error_stream=error_output,
    )

    payload = json.loads(error_output.getvalue())

    assert exit_code == 1
    assert payload["error"]["kind"] == "invalid_path"
    assert destination.read_text(
        encoding="utf-8"
    ) == '{"existing":true}\n'


def test_main_export_overwrites_existing_file(
    tmp_path: Path,
) -> None:
    """Explicit overwrite atomically replaces the destination."""
    destination = tmp_path / "health.json"
    destination.write_text(
        '{"existing":true}\n',
        encoding="utf-8",
    )
    transports: list[MockHttpTransport] = []

    exit_code = main(
        [
            "health",
            "--compact",
            "--output-file",
            str(destination),
            "--overwrite",
        ],
        dependency_builder=build_dependency_builder(
            response_content=b'{"status":"healthy"}',
            transports=transports,
        ),
        output_stream=StringIO(),
        error_stream=StringIO(),
    )

    assert exit_code == 0
    assert json.loads(
        destination.read_text(encoding="utf-8")
    ) == {
        "status": "healthy",
    }


def test_main_rejects_overwrite_without_output_file() -> None:
    """Invalid export configuration fails before dependencies exist."""
    called = False
    error_output = StringIO()

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
            "--overwrite",
        ],
        dependency_builder=forbidden_builder,
        output_stream=StringIO(),
        error_stream=error_output,
    )

    assert exit_code == 2
    assert called is False
    assert (
        "overwrite requires an output file"
        in error_output.getvalue()
    )


def test_main_preserves_stdout_without_output_file() -> None:
    """Legacy stdout behavior remains unchanged without export."""
    transports: list[MockHttpTransport] = []
    output = StringIO()

    exit_code = main(
        [
            "health",
            "--compact",
        ],
        dependency_builder=build_dependency_builder(
            response_content=(
                b'{"status":"healthy","service":"dashboard"}'
            ),
            transports=transports,
        ),
        output_stream=output,
        error_stream=StringIO(),
    )

    assert exit_code == 0
    assert output.getvalue() == (
        '{"service":"dashboard","status":"healthy"}\n'
    )
