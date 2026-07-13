"""HTTP transport implementation for Pipeline Dashboard API Client."""

from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from types import TracebackType
from typing import Self

import httpx

from pipeline_dashboard_api_client.contracts import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    Headers,
    JsonScalar,
)


class HttpTransport:
    """Synchronous HTTP transport backed by httpx."""

    _RETRYABLE_STATUS_CODES = frozenset({502, 503, 504})

    def __init__(
        self,
        config: ApiClientConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        """Initialize the transport.

        An externally supplied client remains owned by the caller. A client
        created internally is closed when the transport is closed.
        """
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
        )
        self._closed = False

    @property
    def config(self) -> ApiClientConfig:
        """Return the transport configuration."""
        return self._config

    @property
    def is_closed(self) -> bool:
        """Return whether the transport has been closed."""
        return self._closed

    def execute(self, request: ApiRequest) -> ApiResponse[bytes]:
        """Execute a normalized API request.

        Connection failures, timeout failures, and retryable gateway/service
        responses are retried according to ``config.max_retries``.
        """
        self._ensure_open()

        url = self._build_url(request.path)
        headers = self._merge_headers(request.headers)
        params = self._encode_query(request.query)
        total_attempts = self._config.max_retries + 1
        started_at = perf_counter()

        for attempt in range(1, total_attempts + 1):
            try:
                response = self._client.request(
                    method=request.method.value,
                    url=url,
                    params=params,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt < total_attempts:
                    continue

                raise self._build_transport_error(
                    kind=ErrorKind.TIMEOUT,
                    message="dashboard API request timed out",
                    details={
                        "attempts": attempt,
                        "url": url,
                    },
                ) from exc
            except httpx.RequestError as exc:
                if attempt < total_attempts:
                    continue

                raise self._build_transport_error(
                    kind=ErrorKind.CONNECTION,
                    message="dashboard API connection failed",
                    details={
                        "attempts": attempt,
                        "url": url,
                    },
                ) from exc

            request_id = self._extract_request_id(response.headers)

            if (
                response.status_code in self._RETRYABLE_STATUS_CODES
                and attempt < total_attempts
            ):
                continue

            elapsed_ms = (perf_counter() - started_at) * 1000

            if response.is_error:
                raise self._build_transport_error(
                    kind=ErrorKind.HTTP,
                    message=(
                        "dashboard API returned HTTP "
                        f"{response.status_code}"
                    ),
                    status_code=response.status_code,
                    request_id=request_id,
                    details={
                        "attempts": attempt,
                        "url": url,
                    },
                )

            return ApiResponse(
                status_code=response.status_code,
                data=response.content,
                headers=dict(response.headers),
                request_id=request_id,
                elapsed_ms=elapsed_ms,
            )

        raise AssertionError("HTTP transport retry loop exited unexpectedly")

    def close(self) -> None:
        """Close the internally owned HTTP client."""
        if self._closed:
            return

        if self._owns_client:
            self._client.close()

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

    def _build_url(self, path: str) -> str:
        """Build an absolute request URL."""
        return f"{self._config.base_url}{path}"

    def _merge_headers(self, request_headers: Headers) -> Headers:
        """Merge configured and request-specific HTTP headers."""
        headers = dict(self._config.default_headers)
        headers.setdefault("Accept", "application/json")
        headers.setdefault("User-Agent", self._config.user_agent)
        headers.update(request_headers)
        return headers

    @staticmethod
    def _encode_query(
        query: Mapping[str, JsonScalar],
    ) -> dict[str, str]:
        """Convert typed query values into HTTP query strings."""
        encoded: dict[str, str] = {}

        for name, value in query.items():
            if value is None:
                continue

            if isinstance(value, bool):
                encoded[name] = "true" if value else "false"
            else:
                encoded[name] = str(value)

        return encoded

    @staticmethod
    def _extract_request_id(headers: httpx.Headers) -> str | None:
        """Extract a request identifier from common response headers."""
        value = headers.get("x-request-id")
        if value is None:
            value = headers.get("x-correlation-id")

        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _build_transport_error(
        *,
        kind: ErrorKind,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
        details: dict[str, JsonScalar] | None = None,
    ) -> DashboardApiClientError:
        """Build a normalized dashboard API client exception."""
        return DashboardApiClientError(
            ApiErrorPayload(
                kind=kind,
                message=message,
                status_code=status_code,
                request_id=request_id,
                details=details or {},
            )
        )

    def _ensure_open(self) -> None:
        """Reject operations after the transport has been closed."""
        if self._closed:
            raise RuntimeError("HTTP transport is closed")
