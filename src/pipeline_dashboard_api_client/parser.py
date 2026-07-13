"""JSON response parsing for the Pipeline Dashboard API Client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeAlias, TypeVar, cast

from pipeline_dashboard_api_client.contracts import (
    ApiErrorPayload,
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    JsonScalar,
)

JsonValue: TypeAlias = (
    JsonScalar
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)
JsonObject: TypeAlias = dict[str, JsonValue]
SourceDataT = TypeVar("SourceDataT")
ParsedDataT = TypeVar("ParsedDataT")


@dataclass(frozen=True, slots=True)
class DashboardDocument:
    """Normalized dashboard endpoint document."""

    payload: JsonObject
    status: str | None = None
    schema_version: str | None = None
    generated_at: str | None = None


@dataclass(frozen=True, slots=True)
class SummaryDocument:
    """Normalized summary endpoint document."""

    payload: JsonObject
    status: str | None = None
    overall_status: str | None = None
    generated_at: str | None = None


@dataclass(frozen=True, slots=True)
class HealthDocument:
    """Normalized health endpoint document."""

    payload: JsonObject
    status: str
    service: str | None = None
    version: str | None = None


class ResponseParser:
    """Parse raw API response bytes into validated typed documents."""

    def parse_object(
        self,
        response: ApiResponse[bytes],
    ) -> ApiResponse[JsonObject]:
        """Decode a response body and require a JSON object root."""
        payload = self._decode_json_object(
            response.data,
            request_id=response.request_id,
            status_code=response.status_code,
        )

        return ApiResponse(
            status_code=response.status_code,
            data=payload,
            headers=response.headers,
            request_id=response.request_id,
            elapsed_ms=response.elapsed_ms,
        )

    def parse_dashboard(
        self,
        response: ApiResponse[bytes],
    ) -> ApiResponse[DashboardDocument]:
        """Parse a dashboard endpoint response."""
        parsed = self.parse_object(response)
        payload = parsed.data

        document = DashboardDocument(
            payload=payload,
            status=self._optional_string(
                payload,
                "status",
                fallback_key="overall_status",
            ),
            schema_version=self._optional_string(
                payload,
                "schema_version",
            ),
            generated_at=self._optional_string(
                payload,
                "generated_at",
            ),
        )

        return self._replace_data(parsed, document)

    def parse_summary(
        self,
        response: ApiResponse[bytes],
    ) -> ApiResponse[SummaryDocument]:
        """Parse a dashboard summary endpoint response."""
        parsed = self.parse_object(response)
        payload = parsed.data

        document = SummaryDocument(
            payload=payload,
            status=self._optional_string(payload, "status"),
            overall_status=self._optional_string(
                payload,
                "overall_status",
                fallback_key="status",
            ),
            generated_at=self._optional_string(
                payload,
                "generated_at",
            ),
        )

        return self._replace_data(parsed, document)

    def parse_health(
        self,
        response: ApiResponse[bytes],
    ) -> ApiResponse[HealthDocument]:
        """Parse and validate a health endpoint response."""
        parsed = self.parse_object(response)
        payload = parsed.data

        status = self._required_string(
            payload,
            "status",
            request_id=response.request_id,
            status_code=response.status_code,
        )

        document = HealthDocument(
            payload=payload,
            status=status,
            service=self._optional_string(payload, "service"),
            version=self._optional_string(payload, "version"),
        )

        return self._replace_data(parsed, document)

    @staticmethod
    def _decode_json_object(
        content: bytes,
        *,
        request_id: str | None,
        status_code: int,
    ) -> JsonObject:
        """Decode UTF-8 JSON and require an object root."""
        if not content:
            raise ResponseParser._error(
                kind=ErrorKind.DECODING,
                message="dashboard API response body is empty",
                request_id=request_id,
                status_code=status_code,
            )

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ResponseParser._error(
                kind=ErrorKind.DECODING,
                message="dashboard API response is not valid UTF-8",
                request_id=request_id,
                status_code=status_code,
            ) from exc

        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResponseParser._error(
                kind=ErrorKind.DECODING,
                message="dashboard API response is not valid JSON",
                request_id=request_id,
                status_code=status_code,
                details={
                    "line": exc.lineno,
                    "column": exc.colno,
                },
            ) from exc

        if not isinstance(decoded, dict):
            raise ResponseParser._error(
                kind=ErrorKind.VALIDATION,
                message="dashboard API response root must be a JSON object",
                request_id=request_id,
                status_code=status_code,
                details={
                    "root_type": type(decoded).__name__,
                },
            )

        return cast(JsonObject, decoded)

    @staticmethod
    def _optional_string(
        payload: JsonObject,
        key: str,
        *,
        fallback_key: str | None = None,
    ) -> str | None:
        """Read and normalize an optional string field."""
        value = payload.get(key)

        if value is None and fallback_key is not None:
            value = payload.get(fallback_key)

        if not isinstance(value, str):
            return None

        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _required_string(
        payload: JsonObject,
        key: str,
        *,
        request_id: str | None,
        status_code: int,
    ) -> str:
        """Read and validate a required non-empty string field."""
        value = payload.get(key)

        if not isinstance(value, str) or not value.strip():
            raise ResponseParser._error(
                kind=ErrorKind.VALIDATION,
                message=f"dashboard API field '{key}' must be a non-empty string",
                request_id=request_id,
                status_code=status_code,
                details={
                    "field": key,
                },
            )

        return value.strip()

    @staticmethod
    def _replace_data(
        response: ApiResponse[SourceDataT],
        data: ParsedDataT,
    ) -> ApiResponse[ParsedDataT]:
        """Return a response preserving metadata with replaced data."""
        return ApiResponse(
            status_code=response.status_code,
            data=data,
            headers=response.headers,
            request_id=response.request_id,
            elapsed_ms=response.elapsed_ms,
        )

    @staticmethod
    def _error(
        *,
        kind: ErrorKind,
        message: str,
        request_id: str | None,
        status_code: int,
        details: dict[str, JsonScalar] | None = None,
    ) -> DashboardApiClientError:
        """Build a normalized parser exception."""
        return DashboardApiClientError(
            ApiErrorPayload(
                kind=kind,
                message=message,
                status_code=status_code,
                request_id=request_id,
                details=details or {},
            )
        )
