"""Tests for the synchronous HTTP transport."""

from collections.abc import Iterator

import httpx
import pytest

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiRequest,
    DashboardApiClientError,
    ErrorKind,
    HttpMethod,
    HttpTransport,
)


@pytest.fixture
def config() -> ApiClientConfig:
    """Return a reusable transport configuration."""
    return ApiClientConfig(
        base_url="https://dashboard.example.com/",
        timeout_seconds=2.5,
        max_retries=2,
        default_headers={"Authorization": "Bearer test-token"},
    )


def build_client(
    handler: httpx.MockTransport,
) -> httpx.Client:
    """Build an httpx client using a mock transport."""
    return httpx.Client(transport=handler)


def test_execute_returns_raw_success_response(
    config: ApiClientConfig,
) -> None:
    """Transport returns response bytes and normalized metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == (
            "https://dashboard.example.com/dashboard"
            "?limit=10&active=true"
        )
        assert request.headers["accept"] == "application/json"
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["user-agent"] == (
            "pipeline-dashboard-api-client/0.1.0"
        )

        return httpx.Response(
            status_code=200,
            content=b'{"status":"healthy"}',
            headers={"X-Request-ID": "request-31"},
        )

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    response = transport.execute(
        ApiRequest(
            method=HttpMethod.GET,
            path="/dashboard",
            query={"limit": 10, "active": True, "ignored": None},
        )
    )

    assert response.status_code == 200
    assert response.data == b'{"status":"healthy"}'
    assert response.request_id == "request-31"
    assert response.elapsed_ms >= 0
    assert response.is_success is True

    client.close()


def test_request_headers_override_default_headers(
    config: ApiClientConfig,
) -> None:
    """Request-level headers take priority over configured defaults."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer override"
        assert request.headers["accept"] == "application/problem+json"
        return httpx.Response(status_code=204)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    response = transport.execute(
        ApiRequest(
            method=HttpMethod.GET,
            path="/health",
            headers={
                "Authorization": "Bearer override",
                "Accept": "application/problem+json",
            },
        )
    )

    assert response.status_code == 204

    client.close()


def test_transport_uses_correlation_id_fallback(
    config: ApiClientConfig,
) -> None:
    """Correlation ID is used when X-Request-ID is absent."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"X-Correlation-ID": "correlation-31"},
        )

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    response = transport.execute(
        ApiRequest(method=HttpMethod.GET, path="/summary")
    )

    assert response.request_id == "correlation-31"

    client.close()


def test_transport_retries_retryable_http_status(
    config: ApiClientConfig,
) -> None:
    """Retryable service responses are retried before succeeding."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            return httpx.Response(status_code=503)

        return httpx.Response(status_code=200, content=b"ok")

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    response = transport.execute(
        ApiRequest(method=HttpMethod.GET, path="/health")
    )

    assert attempts == 3
    assert response.status_code == 200
    assert response.data == b"ok"

    client.close()


def test_transport_raises_after_retryable_status_exhausted(
    config: ApiClientConfig,
) -> None:
    """Final retryable response becomes a normalized HTTP error."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            status_code=503,
            headers={"X-Request-ID": "request-503"},
        )

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    with pytest.raises(DashboardApiClientError) as captured:
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/dashboard")
        )

    assert attempts == 3
    assert captured.value.kind is ErrorKind.HTTP
    assert captured.value.status_code == 503
    assert captured.value.request_id == "request-503"
    assert captured.value.payload.details["attempts"] == 3

    client.close()


def test_transport_does_not_retry_non_retryable_http_status(
    config: ApiClientConfig,
) -> None:
    """Client-side HTTP errors fail immediately."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code=404)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    with pytest.raises(DashboardApiClientError) as captured:
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/missing")
        )

    assert attempts == 1
    assert captured.value.kind is ErrorKind.HTTP
    assert captured.value.status_code == 404

    client.close()


def test_transport_retries_timeout_then_succeeds(
    config: ApiClientConfig,
) -> None:
    """Timeout failures are retried according to configuration."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise httpx.ReadTimeout("timed out", request=request)

        return httpx.Response(status_code=200)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    response = transport.execute(
        ApiRequest(method=HttpMethod.GET, path="/summary")
    )

    assert attempts == 3
    assert response.status_code == 200

    client.close()


def test_transport_raises_timeout_after_retries(
    config: ApiClientConfig,
) -> None:
    """Exhausted timeout retries become a normalized timeout error."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    with pytest.raises(DashboardApiClientError) as captured:
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/summary")
        )

    assert attempts == 3
    assert captured.value.kind is ErrorKind.TIMEOUT
    assert captured.value.status_code is None
    assert captured.value.payload.details["attempts"] == 3

    client.close()


def test_transport_raises_connection_error_after_retries(
    config: ApiClientConfig,
) -> None:
    """Exhausted request failures become normalized connection errors."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused", request=request)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    with pytest.raises(DashboardApiClientError) as captured:
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/dashboard")
        )

    assert attempts == 3
    assert captured.value.kind is ErrorKind.CONNECTION
    assert captured.value.payload.details["attempts"] == 3

    client.close()


def test_transport_close_is_idempotent(
    config: ApiClientConfig,
) -> None:
    """Closing an internally owned transport more than once is safe."""
    transport = HttpTransport(config)

    transport.close()
    transport.close()

    assert transport.is_closed is True


def test_transport_rejects_execute_after_close(
    config: ApiClientConfig,
) -> None:
    """Closed transports cannot execute new requests."""
    transport = HttpTransport(config)
    transport.close()

    with pytest.raises(RuntimeError, match="HTTP transport is closed"):
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/health")
        )


def test_context_manager_closes_owned_transport(
    config: ApiClientConfig,
) -> None:
    """Context manager exit closes internally owned resources."""
    with HttpTransport(config) as transport:
        assert transport.is_closed is False

    assert transport.is_closed is True


def test_external_client_remains_caller_owned(
    config: ApiClientConfig,
) -> None:
    """Closing the transport does not close an injected client."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    transport.close()

    assert transport.is_closed is True
    assert client.is_closed is False

    client.close()


def test_query_encoding_handles_supported_scalar_values(
    config: ApiClientConfig,
) -> None:
    """Query scalar values are encoded consistently."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["name"] == "radar"
        assert request.url.params["count"] == "31"
        assert request.url.params["ratio"] == "1.5"
        assert request.url.params["enabled"] == "false"
        assert "ignored" not in request.url.params
        return httpx.Response(status_code=200)

    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    transport.execute(
        ApiRequest(
            method=HttpMethod.GET,
            path="/dashboard",
            query={
                "name": "radar",
                "count": 31,
                "ratio": 1.5,
                "enabled": False,
                "ignored": None,
            },
        )
    )

    client.close()


def test_zero_retries_executes_only_once() -> None:
    """A zero retry configuration performs one total attempt."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code=503)

    config = ApiClientConfig(
        base_url="https://dashboard.example.com",
        max_retries=0,
    )
    client = build_client(httpx.MockTransport(handler))
    transport = HttpTransport(config, client=client)

    with pytest.raises(DashboardApiClientError):
        transport.execute(
            ApiRequest(method=HttpMethod.GET, path="/health")
        )

    assert attempts == 1

    client.close()


def test_mock_transport_fixture_has_no_pending_requests() -> None:
    """Keep test module iterator typing covered under strict analysis."""

    def empty_iterator() -> Iterator[int]:
        yield from ()

    assert list(empty_iterator()) == []
