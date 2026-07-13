"""Tests for CLI output rendering and printing."""

from io import StringIO

import pytest

from pipeline_dashboard_api_client import (
    ApiErrorPayload,
    DashboardApiClientError,
    ErrorKind,
)
from pipeline_dashboard_api_client.cli.config import OutputMode
from pipeline_dashboard_api_client.cli.printer import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    build_error_document,
    print_error,
    print_json,
    print_message,
    render_json,
)


def test_exit_code_constants_are_stable() -> None:
    """CLI exit-code conventions remain explicit and stable."""
    assert EXIT_SUCCESS == 0
    assert EXIT_FAILURE == 1
    assert EXIT_USAGE_ERROR == 2


def test_render_json_pretty_mode() -> None:
    """Pretty mode renders sorted indented JSON."""
    rendered = render_json(
        {
            "status": "healthy",
            "count": 31,
        },
        output_mode=OutputMode.PRETTY,
    )

    assert rendered == (
        '{\n'
        '  "count": 31,\n'
        '  "status": "healthy"\n'
        '}'
    )


def test_render_json_compact_mode() -> None:
    """Compact mode renders JSON without unnecessary whitespace."""
    rendered = render_json(
        {
            "status": "healthy",
            "count": 31,
        },
        output_mode=OutputMode.COMPACT,
    )

    assert rendered == (
        '{"count":31,"status":"healthy"}'
    )


def test_render_json_preserves_unicode() -> None:
    """JSON rendering does not escape readable Unicode text."""
    rendered = render_json(
        {
            "message": "RADAR hoạt động tốt",
        },
        output_mode=OutputMode.COMPACT,
    )

    assert rendered == (
        '{"message":"RADAR hoạt động tốt"}'
    )


def test_print_json_writes_to_explicit_stream() -> None:
    """JSON output can be redirected for testing and integration."""
    stream = StringIO()

    print_json(
        {
            "status": "ok",
        },
        output_mode=OutputMode.COMPACT,
        stream=stream,
    )

    assert stream.getvalue() == (
        '{"status":"ok"}\n'
    )


def test_print_json_uses_stdout_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Normal JSON documents are written to stdout."""
    print_json(
        {
            "status": "ok",
        },
        output_mode=OutputMode.COMPACT,
    )

    captured = capsys.readouterr()

    assert captured.out == '{"status":"ok"}\n'
    assert captured.err == ""


def test_print_message_normalizes_whitespace() -> None:
    """Human-readable messages are stripped before printing."""
    stream = StringIO()

    print_message(
        "  Dashboard backend reachable.  ",
        stream=stream,
    )

    assert stream.getvalue() == (
        "Dashboard backend reachable.\n"
    )


@pytest.mark.parametrize(
    "message",
    [
        "",
        "   ",
        "\n\t",
    ],
)
def test_print_message_rejects_empty_text(
    message: str,
) -> None:
    """Empty human-readable messages are rejected."""
    with pytest.raises(
        ValueError,
        match="message must not be empty",
    ):
        print_message(message)


def build_client_error() -> DashboardApiClientError:
    """Build a reusable normalized client error."""
    return DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.HTTP,
            message="dashboard backend unavailable",
            status_code=503,
            request_id="request-503",
            details={
                "attempts": 3,
                "retryable": True,
            },
        )
    )


def test_build_error_document_contains_metadata() -> None:
    """Structured errors retain normalized client metadata."""
    document = build_error_document(
        build_client_error()
    )

    assert document == {
        "error": {
            "kind": "http",
            "message": "dashboard backend unavailable",
            "status_code": 503,
            "request_id": "request-503",
            "details": {
                "attempts": 3,
                "retryable": True,
            },
        }
    }


def test_error_document_omits_absent_optional_metadata() -> None:
    """Missing status and request identifiers are omitted."""
    error = DashboardApiClientError(
        ApiErrorPayload(
            kind=ErrorKind.TIMEOUT,
            message="request timed out",
        )
    )

    document = build_error_document(error)

    assert document == {
        "error": {
            "kind": "timeout",
            "message": "request timed out",
        }
    }


def test_print_error_uses_stderr_by_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Structured failures are written to stderr."""
    print_error(
        build_client_error(),
        output_mode=OutputMode.COMPACT,
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == (
        '{"error":{"details":{"attempts":3,'
        '"retryable":true},"kind":"http",'
        '"message":"dashboard backend unavailable",'
        '"request_id":"request-503",'
        '"status_code":503}}\n'
    )


def test_print_error_supports_pretty_output() -> None:
    """Errors support the same pretty mode as normal documents."""
    stream = StringIO()

    print_error(
        build_client_error(),
        output_mode=OutputMode.PRETTY,
        stream=stream,
    )

    rendered = stream.getvalue()

    assert rendered.startswith("{\n")
    assert '"kind": "http"' in rendered
    assert '"status_code": 503' in rendered
    assert rendered.endswith("}\n")
