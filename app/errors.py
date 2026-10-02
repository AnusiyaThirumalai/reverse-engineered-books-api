"""Domain errors. Each maps to one HTTP status and one stable error code."""

from __future__ import annotations


class AppError(Exception):
    """Base class for errors that are safe to show to API consumers."""

    status_code: int = 500
    error: str = "internal_error"

    def __init__(self, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers or {}


class BadRequestError(AppError):
    status_code = 400
    error = "bad_request"


class NotFoundError(AppError):
    status_code = 404
    error = "not_found"


class RateLimitedError(AppError):
    status_code = 429
    error = "rate_limited"


class UpstreamBadResponseError(AppError):
    """Target site answered, but not with something we can use (HTTP 502)."""

    status_code = 502
    error = "upstream_bad_response"


class UpstreamUnavailableError(AppError):
    """Target site could not be reached or is temporarily down (HTTP 503)."""

    status_code = 503
    error = "upstream_unavailable"


class ParseError(UpstreamBadResponseError):
    """HTML did not have the structure the parser expects (selectors drifted)."""

    error = "upstream_parse_error"
