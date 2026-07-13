"""Tests for dashboard API client contracts."""

import pytest

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    HttpMethod,
)


def test_config_normalizes_base_url_and_user_agent() -> None:
    """Configuration strips surrounding spaces and trailing slashes."""
    config = ApiClientConfig(
        base_url=" https://dashboard.example.com/ ",
        user_agent=" radar-client-test ",
    )

    assert config.base_url == "https://dashboard.example.com"
    assert config.user_agent == "radar-client-test"


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "   ",
        "dashboard.example.com",
        "ftp://dashboard.example.com",
        "https://",
    ],
)
def test_config_rejects_invalid_base_url(base_url: str) -> None:
    """Configuration requires a valid HTTP or HTTPS base URL."""
    with pytest.raises(ValueError):
        ApiClientConfig(base_url=base_url)


@pytest.mark.parametrize("timeout_seconds", [0.0, -0.1])
def test_config_rejects_invalid_timeout(timeout_seconds: float) -> None:
    """Timeout must be greater than zero."""
    with pytest.raises(ValueError, match="timeout_seconds"):
        ApiClientConfig(
            base_url="https://dashboard.example.com",
            timeout_seconds=timeout_seconds,
        )


def test_config_rejects_negative_retry_count() -> None:
    """Retry count must not be negative."""
    with pytest.raises(ValueError, match="max_retries"):
        ApiClientConfig(
            base_url="https://dashboard.example.com",
            max_retries=-1,
        )


def test_config_copies_default_headers() -> None:
    """Configuration does not retain a mutable caller-owned header mapping."""
    headers = {"Authorization": "Bearer test"}

    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
        default_headers=headers,
    )
    headers["Authorization"] = "changed"

    assert config.default_headers["Authorization"] == "Bearer test"


def test_request_accepts_dashboard_get_request() -> None:
    """A valid dashboard request preserves typed request data."""
    request = ApiRequest(
        method=HttpMethod.GET,
        path="/dashboard",
        query={"limit": 10, "active": True},
        headers={"Accept": "application/json"},
    )

    assert request.method is HttpMethod.GET
    assert request.path == "/dashboard"
    assert request.query == {"limit": 10, "active": True}
    assert request.headers == {"Accept": "application/json"}


@pytest.mark.parametrize("path", ["", "dashboard", " dashboard "])
def test_request_rejects_invalid_path(path: str) -> None:
    """Request paths must be non-empty absolute API paths."""
    with pytest.raises(ValueError, match="path"):
        ApiRequest(method=HttpMethod.GET, path=path)


def test_response_reports_success_status() -> None:
    """Successful responses expose is_success as true."""
    response = ApiResponse(
        status_code=200,
        data={"status": "healthy"},
        request_id=" request-31 ",
        elapsed_ms=12.5,
    )

    assert response.is_success is True
    assert response.request_id == "request-31"


def test_response_reports_non_success_status() -> None:
    """Non-2xx responses expose is_success as false."""
    response = ApiResponse(
        status_code=503,
        data={"status": "unavailable"},
    )

    assert response.is_success is False


@pytest.mark.parametrize("status_code", [99, 600])
def test_response_rejects_invalid_status_code(status_code: int) -> None:
    """Responses require a valid three-digit HTTP status code."""
    with pytest.raises(ValueError, match="status_code"):
        ApiResponse(status_code=status_code, data=None)


def test_response_rejects_negative_elapsed_time() -> None:
    """Response elapsed time cannot be negative."""
    with pytest.raises(ValueError, match="elapsed_ms"):
        ApiResponse(
            status_code=200,
            data=None,
            elapsed_ms=-1.0,
        )


def test_error_payload_normalizes_values() -> None:
    """Error payloads normalize message and optional request identifiers."""
    payload = ApiErrorPayload(
        kind=ErrorKind.HTTP,
        message=" backend unavailable ",
        status_code=503,
        request_id=" request-503 ",
        details={"retryable": True},
    )

    assert payload.message == "backend unavailable"
    assert payload.request_id == "request-503"
    assert payload.details == {"retryable": True}


def test_dashboard_api_client_error_exposes_payload() -> None:
    """Client exceptions expose normalized payload properties."""
    payload = ApiErrorPayload(
        kind=ErrorKind.TIMEOUT,
        message="request timed out",
        request_id="request-timeout",
    )

    error = DashboardApiClientError(payload)

    assert str(error) == "request timed out"
    assert error.payload is payload
    assert error.kind is ErrorKind.TIMEOUT
    assert error.status_code is None
    assert error.request_id == "request-timeout"
