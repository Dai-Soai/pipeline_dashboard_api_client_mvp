"""Shared structural protocols for Pipeline Dashboard API Client CLI."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pipeline_dashboard_api_client.contracts import (
    ApiResponse,
    Headers,
    QueryParameters,
)


class DashboardCommandClient(Protocol):
    """Client capabilities required by dashboard API commands."""

    def get_dashboard(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the complete dashboard representation."""
        ...

    def get_summary(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the dashboard summary representation."""
        ...

    def get_health(
        self,
        *,
        query: QueryParameters | None = None,
        headers: Headers | None = None,
    ) -> ApiResponse[bytes]:
        """Fetch the dashboard health representation."""
        ...


@runtime_checkable
class ManagedClient(DashboardCommandClient, Protocol):
    """Dashboard command client whose lifecycle can be managed."""

    @property
    def is_closed(self) -> bool:
        """Return whether the client has been closed."""
        ...

    def close(self) -> None:
        """Close client-owned resources."""
        ...
