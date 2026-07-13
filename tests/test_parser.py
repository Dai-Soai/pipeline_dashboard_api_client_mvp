"""Tests for dashboard API response parsing."""

import pytest

from pipeline_dashboard_api_client import (
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    ResponseParser,
)


def build_response(
    content: bytes,
    *,
    status_code: int = 200,
    request_id: str | None = "request-parser-31",
) -> ApiResponse[bytes]:
    """Build a reusable raw API response."""
    return ApiResponse(
        status_code=status_code,
        data=content,
        headers={"content-type": "application/json"},
        request_id=request_id,
        elapsed_ms=4.5,
    )


def test_parse_object_decodes_json_object() -> None:
    """Object parser returns decoded JSON and preserves metadata."""
    parser = ResponseParser()

    response = parser.parse_object(
        build_response(b'{"status":"ok","count":31}')
    )

    assert response.data == {
        "status": "ok",
        "count": 31,
    }
    assert response.status_code == 200
    assert response.request_id == "request-parser-31"
    assert response.elapsed_ms == 4.5


def test_parse_dashboard_normalizes_metadata() -> None:
    """Dashboard parser extracts common dashboard metadata."""
    parser = ResponseParser()

    response = parser.parse_dashboard(
        build_response(
            b'{"status":" warning ",'
            b'"schema_version":" 1.0 ",'
            b'"generated_at":" 2026-07-13T21:00:00Z ",'
            b'"panels":[]}'
        )
    )

    assert response.data.status == "warning"
    assert response.data.schema_version == "1.0"
    assert response.data.generated_at == "2026-07-13T21:00:00Z"
    assert response.data.payload["panels"] == []


def test_dashboard_uses_overall_status_fallback() -> None:
    """Dashboard parser falls back to overall_status."""
    parser = ResponseParser()

    response = parser.parse_dashboard(
        build_response(b'{"overall_status":"healthy"}')
    )

    assert response.data.status == "healthy"


def test_parse_summary_normalizes_summary_fields() -> None:
    """Summary parser extracts normalized summary metadata."""
    parser = ResponseParser()

    response = parser.parse_summary(
        build_response(
            b'{"status":"ok",'
            b'"overall_status":" healthy ",'
            b'"generated_at":"now"}'
        )
    )

    assert response.data.status == "ok"
    assert response.data.overall_status == "healthy"
    assert response.data.generated_at == "now"


def test_summary_uses_status_fallback() -> None:
    """Summary overall status falls back to status."""
    parser = ResponseParser()

    response = parser.parse_summary(
        build_response(b'{"status":"degraded"}')
    )

    assert response.data.overall_status == "degraded"


def test_parse_health_requires_and_normalizes_status() -> None:
    """Health parser requires a non-empty status field."""
    parser = ResponseParser()

    response = parser.parse_health(
        build_response(
            b'{"status":" healthy ",'
            b'"service":" dashboard-backend ",'
            b'"version":" 0.1.0 "}'
        )
    )

    assert response.data.status == "healthy"
    assert response.data.service == "dashboard-backend"
    assert response.data.version == "0.1.0"


def test_empty_body_raises_decoding_error() -> None:
    """Empty response bodies become normalized decoding failures."""
    parser = ResponseParser()

    with pytest.raises(DashboardApiClientError) as captured:
        parser.parse_object(build_response(b""))

    assert captured.value.kind is ErrorKind.DECODING
    assert captured.value.status_code == 200
    assert captured.value.request_id == "request-parser-31"


def test_invalid_utf8_raises_decoding_error() -> None:
    """Invalid UTF-8 responses become normalized decoding failures."""
    parser = ResponseParser()

    with pytest.raises(DashboardApiClientError) as captured:
        parser.parse_object(build_response(b"\xff\xfe"))

    assert captured.value.kind is ErrorKind.DECODING
    assert "UTF-8" in str(captured.value)


def test_invalid_json_raises_decoding_error() -> None:
    """Malformed JSON becomes a normalized decoding failure."""
    parser = ResponseParser()

    with pytest.raises(DashboardApiClientError) as captured:
        parser.parse_object(build_response(b'{"status":'))

    assert captured.value.kind is ErrorKind.DECODING
    assert captured.value.payload.details["line"] == 1


@pytest.mark.parametrize(
    "content",
    [
        b"[]",
        b'"healthy"',
        b"31",
        b"true",
        b"null",
    ],
)
def test_non_object_root_raises_validation_error(
    content: bytes,
) -> None:
    """Only JSON objects are accepted as endpoint documents."""
    parser = ResponseParser()

    with pytest.raises(DashboardApiClientError) as captured:
        parser.parse_object(build_response(content))

    assert captured.value.kind is ErrorKind.VALIDATION
    assert "root" in str(captured.value)


@pytest.mark.parametrize(
    "content",
    [
        b"{}",
        b'{"status":null}',
        b'{"status":31}',
        b'{"status":"   "}',
    ],
)
def test_health_rejects_invalid_status(
    content: bytes,
) -> None:
    """Health responses require a non-empty string status."""
    parser = ResponseParser()

    with pytest.raises(DashboardApiClientError) as captured:
        parser.parse_health(build_response(content))

    assert captured.value.kind is ErrorKind.VALIDATION
    assert captured.value.payload.details["field"] == "status"


def test_optional_non_string_fields_normalize_to_none() -> None:
    """Optional fields with incompatible types are ignored."""
    parser = ResponseParser()

    response = parser.parse_dashboard(
        build_response(
            b'{"status":31,"schema_version":true,"generated_at":[]}'
        )
    )

    assert response.data.status is None
    assert response.data.schema_version is None
    assert response.data.generated_at is None
