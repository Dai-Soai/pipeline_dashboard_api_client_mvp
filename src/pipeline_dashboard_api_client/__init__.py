"""Pipeline Dashboard API Client.

A typed client package for communicating with the RADAR_SERVICE
Pipeline Dashboard Backend.
"""

from pipeline_dashboard_api_client.client import (
    DashboardClient,
    DashboardTransport,
)
from pipeline_dashboard_api_client.contracts import (
    ApiClientConfig,
    ApiErrorPayload,
    ApiRequest,
    ApiResponse,
    DashboardApiClientError,
    ErrorKind,
    Headers,
    HttpMethod,
    JsonScalar,
    QueryParameters,
)
from pipeline_dashboard_api_client.parser import (
    DashboardDocument,
    HealthDocument,
    JsonObject,
    JsonValue,
    ResponseParser,
    SummaryDocument,
)
from pipeline_dashboard_api_client.transport import HttpTransport
from pipeline_dashboard_api_client.version import __version__

__all__ = [
    "ApiClientConfig",
    "ApiErrorPayload",
    "ApiRequest",
    "ApiResponse",
    "DashboardApiClientError",
    "DashboardClient",
    "DashboardDocument",
    "DashboardTransport",
    "ErrorKind",
    "Headers",
    "HealthDocument",
    "HttpMethod",
    "HttpTransport",
    "JsonObject",
    "JsonScalar",
    "JsonValue",
    "QueryParameters",
    "ResponseParser",
    "SummaryDocument",
    "__version__",
]
