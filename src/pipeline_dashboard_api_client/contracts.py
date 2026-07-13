"""Typed contracts for the Pipeline Dashboard API Client."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Generic, TypeAlias, TypeVar
from urllib.parse import urlparse

JsonScalar: TypeAlias = str | int | float | bool | None
QueryParameters: TypeAlias = dict[str, JsonScalar]
Headers: TypeAlias = dict[str, str]

ResponseDataT = TypeVar("ResponseDataT")


class HttpMethod(StrEnum):
    """HTTP methods supported by the dashboard API client."""

    GET = "GET"


class ErrorKind(StrEnum):
    """Normalized API client error categories."""

    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    CONNECTION = "connection"
    TIMEOUT = "timeout"
    HTTP = "http"
    DECODING = "decoding"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ApiClientConfig:
    """Configuration required to communicate with a dashboard backend."""

    base_url: str
    timeout_seconds: float = 10.0
    max_retries: int = 2
    user_agent: str = "pipeline-dashboard-api-client/0.1.0"
    default_headers: Headers = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize client configuration."""
        normalized_base_url = self.base_url.strip().rstrip("/")
        parsed_url = urlparse(normalized_base_url)

        if not normalized_base_url:
            raise ValueError("base_url must not be empty")

        if parsed_url.scheme not in {"http", "https"}:
            raise ValueError("base_url must use http or https")

        if not parsed_url.netloc:
            raise ValueError("base_url must include a network location")

        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")

        normalized_user_agent = self.user_agent.strip()
        if not normalized_user_agent:
            raise ValueError("user_agent must not be empty")

        normalized_headers: Headers = {}
        for name, value in self.default_headers.items():
            normalized_name = name.strip()
            normalized_value = value.strip()

            if not normalized_name:
                raise ValueError("default header names must not be empty")

            if not normalized_value:
                raise ValueError(
                    f"default header value must not be empty: {normalized_name}"
                )

            normalized_headers[normalized_name] = normalized_value

        object.__setattr__(self, "base_url", normalized_base_url)
        object.__setattr__(self, "user_agent", normalized_user_agent)
        object.__setattr__(self, "default_headers", normalized_headers)


@dataclass(frozen=True, slots=True)
class ApiRequest:
    """Normalized request passed to the HTTP transport layer."""

    method: HttpMethod
    path: str
    query: QueryParameters = field(default_factory=dict)
    headers: Headers = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize request values."""
        normalized_path = self.path.strip()

        if not normalized_path:
            raise ValueError("path must not be empty")

        if not normalized_path.startswith("/"):
            raise ValueError("path must start with '/'")

        normalized_headers: Headers = {}
        for name, value in self.headers.items():
            normalized_name = name.strip()
            normalized_value = value.strip()

            if not normalized_name:
                raise ValueError("request header names must not be empty")

            if not normalized_value:
                raise ValueError(
                    f"request header value must not be empty: {normalized_name}"
                )

            normalized_headers[normalized_name] = normalized_value

        object.__setattr__(self, "path", normalized_path)
        object.__setattr__(self, "query", dict(self.query))
        object.__setattr__(self, "headers", normalized_headers)


@dataclass(frozen=True, slots=True)
class ApiResponse(Generic[ResponseDataT]):
    """Typed response returned by the dashboard API client."""

    status_code: int
    data: ResponseDataT
    headers: Headers = field(default_factory=dict)
    request_id: str | None = None
    elapsed_ms: float = 0.0

    def __post_init__(self) -> None:
        """Validate and normalize response metadata."""
        if not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")

        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative")

        normalized_request_id = self.request_id
        if normalized_request_id is not None:
            normalized_request_id = normalized_request_id.strip()
            if not normalized_request_id:
                normalized_request_id = None

        object.__setattr__(self, "headers", dict(self.headers))
        object.__setattr__(self, "request_id", normalized_request_id)

    @property
    def is_success(self) -> bool:
        """Return whether the response has a successful HTTP status."""
        return 200 <= self.status_code <= 299


@dataclass(frozen=True, slots=True)
class ApiErrorPayload:
    """Serializable normalized error information."""

    kind: ErrorKind
    message: str
    status_code: int | None = None
    request_id: str | None = None
    details: dict[str, JsonScalar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize error payload values."""
        normalized_message = self.message.strip()
        if not normalized_message:
            raise ValueError("message must not be empty")

        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("status_code must be between 100 and 599")

        normalized_request_id = self.request_id
        if normalized_request_id is not None:
            normalized_request_id = normalized_request_id.strip()
            if not normalized_request_id:
                normalized_request_id = None

        object.__setattr__(self, "message", normalized_message)
        object.__setattr__(self, "request_id", normalized_request_id)
        object.__setattr__(self, "details", dict(self.details))


class DashboardApiClientError(Exception):
    """Exception raised for normalized dashboard API client failures."""

    def __init__(self, payload: ApiErrorPayload) -> None:
        """Initialize the exception from an error payload."""
        self.payload = payload
        super().__init__(payload.message)

    @property
    def kind(self) -> ErrorKind:
        """Return the normalized error kind."""
        return self.payload.kind

    @property
    def status_code(self) -> int | None:
        """Return the associated HTTP status code, when available."""
        return self.payload.status_code

    @property
    def request_id(self) -> str | None:
        """Return the associated request identifier, when available."""
        return self.payload.request_id
