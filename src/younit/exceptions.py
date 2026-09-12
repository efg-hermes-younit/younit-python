"""Exception hierarchy for the EFG API Python SDK.

All exceptions raised by this SDK are subclasses of :class:`EFGError`.

Hierarchy::

    EFGError
    ├── AuthError
    │   ├── InvalidCredentials
    │   └── TokenExpired
    ├── APIError                 # HTTP 4xx / 5xx
    │   ├── BadRequest           # 400
    │   ├── Unauthorized         # 401 (after refresh attempt)
    │   ├── Forbidden            # 403
    │   ├── NotFound             # 404
    │   ├── RateLimited          # 429
    │   └── ServerError          # 5xx
    ├── OrderError
    │   ├── OrderRejected
    │   ├── InsufficientFunds
    │   └── InvalidOrder
    ├── InvalidSymbol
    └── ConfigError
"""

from __future__ import annotations

from typing import Any


class EFGError(Exception):
    """Base exception for all errors raised by the EFG API SDK."""

    def __init__(self, message: str, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(message)
        self.message = message
        # Attach any additional context attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.message!r})"


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------


class AuthError(EFGError):
    """Authentication or authorisation failure."""


class InvalidCredentials(AuthError):  # noqa: N818
    """Partner ID or partner secret was rejected by the identity provider."""


class TokenExpired(AuthError):  # noqa: N818
    """A token expired and could not be refreshed automatically."""


# ---------------------------------------------------------------------------
# API errors (HTTP)
# ---------------------------------------------------------------------------


class APIError(EFGError):
    """An HTTP error response was returned by the API.

    Attributes:
        status_code: The HTTP status code.
        response_body: The raw response body string (may be empty).
        request_id: The ``X-Request-Id`` header value, if present.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        response_body: str = "",
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id

    def __repr__(self) -> str:
        return f"{type(self).__name__}(status_code={self.status_code}, message={self.message!r})"


class BadRequest(APIError):  # noqa: N818
    """HTTP 400 — the request was malformed or rejected by the server."""


class Unauthorized(APIError):  # noqa: N818
    """HTTP 401 — authentication failed even after a token refresh attempt."""


class Forbidden(APIError):  # noqa: N818
    """HTTP 403 — authenticated but not authorised for this resource."""


class NotFound(APIError):  # noqa: N818
    """HTTP 404 — the requested resource does not exist."""


class RateLimited(APIError):  # noqa: N818
    """HTTP 429 — too many requests; back off and retry later."""


class ServerError(APIError):
    """HTTP 5xx — the backend returned a server error."""


# ---------------------------------------------------------------------------
# Order errors
# ---------------------------------------------------------------------------


class OrderError(EFGError):
    """Business-logic failure related to order placement or management."""


class OrderRejected(OrderError):  # noqa: N818
    """The exchange or broker rejected the order."""


class InsufficientFunds(OrderError):  # noqa: N818
    """Not enough buying power to place this order."""


class InvalidOrder(OrderError):  # noqa: N818
    """The order parameters are invalid (e.g. price out of allowed range)."""


# ---------------------------------------------------------------------------
# Symbol / config errors
# ---------------------------------------------------------------------------


class InvalidSymbol(EFGError):  # noqa: N818
    """The ticker symbol is not found in the symbol map for this market.

    Attributes:
        symbol: The ticker string that was not found.
        market_id: The market that was searched.
    """

    def __init__(self, symbol: str, market_id: int = 1) -> None:
        super().__init__(
            f"Symbol {symbol!r} not found in market {market_id}. "
            "Call client.refresh_symbols() to rebuild the cache, "
            "or verify the ticker is listed on EGX."
        )
        self.symbol = symbol
        self.market_id = market_id


class ConfigError(EFGError):
    """Required configuration is missing or invalid."""


# ---------------------------------------------------------------------------
# Streaming errors
# ---------------------------------------------------------------------------


class StreamingError(EFGError):
    """Base class for real-time Lightstreamer streaming errors."""


class ConnectionFailed(StreamingError):  # noqa: N818
    """The Lightstreamer connection could not be established or was lost.

    Attributes:
        status: The Lightstreamer status string at the time of failure.
    """

    def __init__(self, message: str, *, status: str = "") -> None:
        super().__init__(message)
        self.status = status


class SubscriptionFailed(StreamingError):  # noqa: N818
    """A Lightstreamer subscription was rejected by the server.

    Attributes:
        code: The Lightstreamer error code.
        error_message: The error message from the server.
    """

    def __init__(self, message: str, *, code: int = 0, error_message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.error_message = error_message
