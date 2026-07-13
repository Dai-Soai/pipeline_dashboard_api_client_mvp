"""Tests for the high-level dashboard API client."""

from __future__ import annotations

from pipeline_dashboard_api_client import (
    ApiClientConfig,
    ApiRequest,
    ApiResponse,
    DashboardClient,
    HttpMethod,
    QueryParameters,
)


class RecordingTransport:
    """Transport double that records requests without network access."""

    def __init__(self) -> None:
        """Initialize the recording transport."""
        self.requests: list[ApiRequest] = []
        self.close_calls = 0
        self.response = ApiResponse(
            status_code=200,
            data=b'{"status":"ok"}',
            headers={"content-type": "application/json"},
            request_id="request-client-31",
            elapsed_ms=1.25,
        )

    def execute(self, request: ApiRequest) -> ApiResponse[bytes]:
        """Record a request and return the configured response."""
        self.requests.append(request)
        return self.response

    def close(self) -> None:
        """Record transport close calls."""
        self.close_calls += 1


def build_config() -> ApiClientConfig:
    """Build reusable dashboard client configuration."""
    return ApiClientConfig(
        base_url="https://dashboard.example.com",
    )


def test_get_dashboard_uses_dashboard_endpoint() -> None:
    """Dashboard requests target GET /dashboard."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    response = client.get_dashboard()

    assert response is transport.response
    assert len(transport.requests) == 1
    assert transport.requests[0].method is HttpMethod.GET
    assert transport.requests[0].path == "/dashboard"


def test_get_summary_uses_summary_endpoint() -> None:
    """Summary requests target GET /summary."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    client.get_summary()

    assert len(transport.requests) == 1
    assert transport.requests[0].method is HttpMethod.GET
    assert transport.requests[0].path == "/summary"


def test_get_health_uses_health_endpoint() -> None:
    """Health requests target GET /health."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    client.get_health()

    assert len(transport.requests) == 1
    assert transport.requests[0].method is HttpMethod.GET
    assert transport.requests[0].path == "/health"


def test_dashboard_request_forwards_query_parameters() -> None:
    """Dashboard query parameters are passed to the transport."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    query: QueryParameters = {
        "status": "warning",
        "limit": 20,
        "active": True,
        "cursor": None,
    }

    client.get_dashboard(query=query)

    assert transport.requests[0].query == query


def test_summary_request_forwards_headers() -> None:
    """Endpoint-specific headers are passed to the transport."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    client.get_summary(
        headers={
            "Accept": "application/json",
            "X-Correlation-ID": "correlation-31",
        }
    )

    assert transport.requests[0].headers == {
        "Accept": "application/json",
        "X-Correlation-ID": "correlation-31",
    }


def test_client_does_not_retain_caller_owned_query_mapping() -> None:
    """Requests copy caller-owned query mappings."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)
    query = {"limit": 10}

    client.get_dashboard(query=query)
    query["limit"] = 50

    assert transport.requests[0].query["limit"] == 10


def test_client_exposes_configuration() -> None:
    """The client exposes its immutable configuration."""
    config = build_config()
    transport = RecordingTransport()

    client = DashboardClient(config, transport=transport)

    assert client.config is config
    assert client.is_closed is False


def test_closing_injected_transport_client_keeps_transport_open() -> None:
    """Injected transports remain owned by the caller."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)

    client.close()
    client.close()

    assert client.is_closed is True
    assert transport.close_calls == 0


def test_closed_client_rejects_endpoint_requests() -> None:
    """No endpoint request may execute after client closure."""
    transport = RecordingTransport()
    client = DashboardClient(build_config(), transport=transport)
    client.close()

    try:
        client.get_health()
    except RuntimeError as error:
        assert str(error) == "dashboard client is closed"
    else:
        raise AssertionError("expected RuntimeError")


def test_context_manager_marks_client_closed() -> None:
    """Context manager exit closes the dashboard client."""
    transport = RecordingTransport()

    with DashboardClient(
        build_config(),
        transport=transport,
    ) as client:
        response = client.get_dashboard()

        assert response.status_code == 200
        assert client.is_closed is False

    assert client.is_closed is True
    assert transport.close_calls == 0
