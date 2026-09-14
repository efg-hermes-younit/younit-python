"""HTTP client construction and configuration for the Younit API SDK.

Constructs a single ``httpx.Client`` per SDK Client instance with:
- HTTP/2 enabled
- Configurable timeouts (connect: 10s, read: configurable, default 30s)
- Retry logic for idempotent methods (GET, DELETE) on 5xx and connection errors
- Standard default headers applied to every request
- Cookie handling enabled (httpx default)

Important: POST /orders is NEVER retried. A timeout on an order must surface
to the caller so they can verify via list_orders whether it landed.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any

import httpx

from younit._version import __version__
from younit.config import Settings
from younit.exceptions import (
    APIError,
    BadRequest,
    Forbidden,
    NotFound,
    RateLimited,
    ServerError,
    Unauthorized,
)
from younit.logging import get_logger

_log = get_logger(__name__)

# Methods that are safe to retry on transient errors
_IDEMPOTENT_METHODS = frozenset({"GET", "DELETE", "HEAD", "OPTIONS"})

# Paths that must NEVER be retried (order placement is irreversible)
_NO_RETRY_PATHS = frozenset({"/api/v1/orders/normal"})

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 0.5  # seconds; doubles each attempt


def _build_user_agent() -> str:
    return f"younit-python/{__version__} (+https://github.com/efg-hermes-younit/younit-python)"


def build_default_headers(settings: Settings) -> dict[str, str]:
    """Build the set of default headers applied to every API request.

    These headers are defined in one place so that updates (e.g. when the
    backend team confirms additional required headers) only need one change.

    Args:
        settings: The active SDK configuration.

    Returns:
        Dict of header name → value.
    """
    return {
        "Accept-Language": settings.accept_language,
        "X-Server-Select": settings.server_select_header,
        "x-company-code": settings.company_code,
        "x-api-version": settings.api_version,
        "User-Agent": _build_user_agent(),
    }


def build_httpx_client(settings: Settings) -> httpx.Client:
    """Construct the ``httpx.Client`` used by the SDK.

    Uses httpx's standard default TLS verification (system CA trust store).
    A pinned single-leaf-cert workaround was used here from 2026-08 to
    2026-09-13 to route around what looked like a broken certificate chain
    on the trading/identity host; live verification on 2026-09-13 confirmed
    the server now sends a complete, valid chain and standard verification
    works end-to-end (see diagnostics/tls_chain_report.py and
    diagnostics/standard_trust_full_flow_test.py), so the pin was removed.
    The retired pinned cert is kept at
    diagnostics/efghermesone-identity-pinned-cert.pem as a rollback safety
    net in case this regresses (e.g. load-balancer node inconsistency).

    The old pinned context also set SECLEVEL=1 to allow legacy ciphers;
    removed here too since the live prod flow succeeded without it (see
    diagnostics/standard_trust_full_flow_test.py). NOTE: that comment
    originally mentioned staging environments needing legacy ciphers,
    which was not separately re-tested — if staging (via
    ``_base_url_override``) ever fails TLS negotiation, this is the first
    thing to suspect.

    Args:
        settings: The active SDK configuration.

    Returns:
        A configured ``httpx.Client`` instance.
        Callers are responsible for closing it (``client.close()``).
    """
    timeout = httpx.Timeout(
        connect=10.0,
        read=settings.timeout_seconds,
        write=settings.timeout_seconds,
        pool=10.0,
    )

    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        # Cookies are enabled by default in httpx.Client
    )


def raise_for_status(response: httpx.Response) -> None:
    """Raise the appropriate :class:`~younit.exceptions.APIError` subclass.

    Args:
        response: The httpx response object.

    Raises:
        BadRequest: On HTTP 400.
        Unauthorized: On HTTP 401.
        Forbidden: On HTTP 403.
        NotFound: On HTTP 404.
        RateLimited: On HTTP 429.
        ServerError: On HTTP 5xx.
        APIError: On any other non-2xx status.
    """
    if response.is_success:
        return

    status = response.status_code
    try:
        body = response.text
    except Exception:
        body = ""

    request_id = response.headers.get("X-Request-Id") or response.headers.get("x-request-id")

    kwargs: dict[str, Any] = {
        "status_code": status,
        "response_body": body,
        "request_id": request_id,
    }

    # Extract message from response body if possible
    message = f"HTTP {status}"
    try:
        data = response.json()
        if isinstance(data, dict):
            # Some endpoints wrap messages in a list
            messages = data.get("messages") or []
            if messages:
                message = "; ".join(str(m) for m in messages)
    except Exception:  # noqa: S110 — best-effort JSON parse; silently skip on malformed body
        pass

    if status == 400:
        raise BadRequest(message, **kwargs)
    if status == 401:
        raise Unauthorized(message, **kwargs)
    if status == 403:
        raise Forbidden(message, **kwargs)
    if status == 404:
        raise NotFound(message, **kwargs)
    if status == 429:
        raise RateLimited(message, **kwargs)
    if status >= 500:
        raise ServerError(message, **kwargs)
    raise APIError(message, **kwargs)


def _should_retry(
    method: str,
    path: str,
    attempt: int,
    exc: Exception | None,
    status: int | None,
) -> bool:
    """Determine whether a request should be retried.

    Args:
        method: HTTP method string.
        path: Request path.
        attempt: Current attempt number (0-indexed).
        exc: Exception raised, if any.
        status: HTTP status code, if response was received.

    Returns:
        True if the request should be retried.
    """
    if attempt >= _MAX_RETRIES:
        return False
    # Never retry non-idempotent methods
    if method.upper() not in _IDEMPOTENT_METHODS:
        return False
    # Never retry order placement paths, even if somehow classified as idempotent
    if any(no_retry in path for no_retry in _NO_RETRY_PATHS):
        return False
    # Retry on connection errors
    if exc is not None and isinstance(
        exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout)
    ):
        return True
    # Retry on 5xx
    if status is not None and status >= 500:
        return True
    return False


@contextmanager
def timed_request(method: str, path: str) -> Generator[dict[str, float], None, None]:
    """Context manager that measures request duration for logging.

    Yields:
        A dict that will be populated with ``duration_ms`` after the block.
    """
    info: dict[str, float] = {}
    start = time.monotonic()
    try:
        yield info
    finally:
        info["duration_ms"] = round((time.monotonic() - start) * 1000, 1)


def execute_with_retry(
    http: httpx.Client,
    method: str,
    url: str,
    path: str,
    *,
    token_getter: Callable[[], str],
    default_headers: dict[str, str],
    **kwargs: Any,  # noqa: ANN401
) -> httpx.Response:
    """Execute an HTTP request with retry logic for idempotent methods.

    Injects the Authorization header on every attempt (so refreshed tokens
    are used transparently on retries).

    Args:
        http: The httpx client instance.
        method: HTTP method string (e.g. ``"GET"``).
        url: Full URL to request.
        path: Path component for retry-eligibility check.
        token_getter: Callable that returns the current bearer token.
            Called on each attempt to pick up any refreshed token.
        default_headers: Base headers to include on every request.
        **kwargs: Additional arguments passed to ``httpx.Client.request``.

    Returns:
        The httpx response.

    Raises:
        APIError subclass on non-retryable HTTP errors.
        httpx.TimeoutException on timeout (never retried for POST /orders).
    """
    attempt = 0
    last_status: int | None = None

    while True:
        if attempt > 0:
            backoff = _RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            _log.warning(
                "retrying_request",
                method=method,
                path=path,
                attempt=attempt,
                backoff_seconds=backoff,
                last_status=last_status,
            )
            time.sleep(backoff)

        headers = {**default_headers}
        headers["Authorization"] = f"Bearer {token_getter()}"

        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        with timed_request(method, path) as timing:
            try:
                response = http.request(method, url, headers=headers, **kwargs)
                last_status = response.status_code

                _log.debug(
                    "http_response",
                    method=method,
                    path=path,
                    status=response.status_code,
                    duration_ms=timing.get("duration_ms"),
                    request_id=response.headers.get("X-Request-Id"),
                )

                if _should_retry(method, path, attempt, None, response.status_code):
                    attempt += 1
                    continue

                return response

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout) as exc:
                _log.warning(
                    "http_transport_error",
                    method=method,
                    path=path,
                    error=str(exc),
                    attempt=attempt,
                )
                if _should_retry(method, path, attempt, exc, None):
                    attempt += 1
                    continue
                raise
