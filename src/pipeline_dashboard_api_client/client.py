"""High-level client for the Pipeline Dashboard Backend."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Protocol, Self

from pipeline_dashboard_api_client.contracts import (
    ApiClientConfig,
    ApiRequest,
    ApiResponse,
    Headers,
    HttpMethod,
    JsonScalar,
    QueryParameters,
)
from pipeline_dashboard_api_client.transport import HttpTransport


class DashboardTransport(Protocol):
    """Transport interface required by the high-level dashboard client."""

    def execute(self, request: ApiRequest) -> ApiResponse[bytes]:
        """Execute a normalized dashboard API request."""
        ...

    def close(self) -> None:
        """Close transport resources."""
        ...


class DashboardClient:
    """High-level synchronous client for dashboard API endpoints."""

    def __init__(
        self,
        config: ApiClientConfig,
        *,
        transport: DashboardTransport | None = None,
    ) -> None:
        """Initialize the dashboard client.

        When no transport is supplied, the client creates and owns an
        ``HttpTransport`` instance. Injected transports remain caller-owned.
        """
        self._config = config
        self._owns_transport = transport is None
        self._transport = transport or HttpTransport(config)
        self._closed = False

    @property
    def config(self) -> ApiClientConfig:
        """Return the dashboard client configuration."""
        return self._config

    @property
    def is_closed(self) -> bool:
        """Return whether the dashboard client has been closed."""
        return self._closed

    def get_dashboard(
        self,
        *,
        query: Mapping[str, JsonScalar] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the complete dashboard representation."""
        return self._get(
            path="/dashboard",
            query=query,
            headers=headers,
        )

    def get_summary(
        self,
        *,
        query: Mapping[str, JsonScalar] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the dashboard summary representation."""
        return self._get(
            path="/summary",
            query=query,
            headers=headers,
        )

    def get_health(
        self,
        *,
        query: Mapping[str, JsonScalar] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the dashboard backend health representation."""
        return self._get(
            path="/health",
            query=query,
            headers=headers,
        )

    def close(self) -> None:
        """Close resources owned by the dashboard client."""
        if self._closed:
            return

        if self._owns_transport:
            self._transport.close()

        self._closed = True

    def __enter__(self) -> Self:
        """Enter the synchronous context manager."""
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the synchronous context manager."""
        self.close()

    def _get(
        self,
        *,
        path: str,
        query: Mapping[str, JsonScalar] | None,
        headers: Mapping[str, str] | None,
    ) -> ApiResponse[bytes]:
        """Execute a GET request against a dashboard endpoint."""
        self._ensure_open()

        normalized_query: QueryParameters = (
            {} if query is None else dict(query)
        )
        normalized_headers: Headers = (
            {} if headers is None else dict(headers)
        )

        request = ApiRequest(
            method=HttpMethod.GET,
            path=path,
            query=normalized_query,
            headers=normalized_headers,
        )

        return self._transport.execute(request)

    def _ensure_open(self) -> None:
        """Reject operations after the client has been closed."""
        if self._closed:
            raise RuntimeError("dashboard client is closed")
