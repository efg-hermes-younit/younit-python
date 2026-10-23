"""Public-key authentication and token lifecycle management.

Tokens are refreshed five minutes before expiry and once after an API 401.
Token lifetimes are read from the response, never hardcoded.
"""

from __future__ import annotations

import re
import time
from typing import Protocol, runtime_checkable

import httpx

from younit.config import _TOKEN_URL, Settings
from younit.exceptions import AuthError, InvalidCredentials, TokenExpired
from younit.http import build_default_headers
from younit.logging import get_logger

_log = get_logger(__name__)
_REFRESH_BUFFER_SECONDS = 300


@runtime_checkable
class TokenStore(Protocol):
    """Protocol for pluggable token storage."""

    def get(self, key: str) -> str | None:
        """Retrieve a token value by key."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store a token value."""
        ...


class InMemoryTokenStore:
    """Keep tokens in memory for the lifetime of the client."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Retrieve a token by key."""
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        """Store a token."""
        self._store[key] = value


class _TokenRecord:
    """Hold a token value, type, and monotonic expiry timestamp."""

    __slots__ = ("expires_at", "token_type", "value")

    def __init__(self, value: str, expires_in: int, token_type: str) -> None:
        self.value = value
        self.token_type = token_type
        self.expires_at = time.monotonic() + expires_in

    def is_expired(self) -> bool:
        """Return True if the token has expired."""
        return time.monotonic() >= self.expires_at

    def needs_refresh(self) -> bool:
        """Return True if the token should be proactively refreshed."""
        return time.monotonic() >= self.expires_at - _REFRESH_BUFFER_SECONDS


def _parse_token_response(response: httpx.Response) -> _TokenRecord:
    """Parse the public-keys token schema, optionally inside ``data``."""
    try:
        top_level = response.json()
    except ValueError:
        raise AuthError(
            f"Token request returned non-JSON data (HTTP {response.status_code})."
        ) from None
    if not isinstance(top_level, dict):
        raise AuthError("Token response must be a JSON object.")
    nested = top_level.get("data")
    payload = nested if isinstance(nested, dict) else top_level
    token = payload.get("accessToken")
    expires_in = payload.get("expiresIn")
    token_type = payload.get("tokenType")
    if not isinstance(token, str) or not token.strip():
        keys = sorted(str(key) for key in top_level)
        raise AuthError(
            f"Token response missing or invalid 'accessToken'; top-level keys received: {keys}."
        )
    if type(expires_in) is not int or expires_in <= 0:
        raise AuthError("Token response missing or invalid 'expiresIn'.")
    if not isinstance(token_type, str) or not token_type.strip():
        raise AuthError("Token response missing or invalid 'tokenType'.")
    return _TokenRecord(token, expires_in, token_type)


class IdentityProvider:
    """Acquire and refresh the client token using the public-keys endpoint."""

    def __init__(
        self,
        settings: Settings,
        http: httpx.Client,
        store: TokenStore | None = None,
    ) -> None:
        self._settings = settings
        self._http = http
        self._store = store or InMemoryTokenStore()
        self._token: _TokenRecord | None = None

    def authenticate(self) -> None:
        """Authenticate using TRADING_ID and API_KEY."""
        self._fetch_token()

    def get_token(self) -> str:
        """Return a valid bearer token, refreshing before expiry."""
        if self._token is None or self._token.needs_refresh():
            _log.info("proactive_token_refresh", reason="expiry_approaching")
            self._fetch_token()
        if self._token is None or self._token.is_expired():
            raise TokenExpired("Token expired and could not be refreshed.")
        return self._token.value

    def get_authorization(self) -> str:
        """Return the current REST Authorization header value."""
        token = self.get_token()
        assert self._token is not None
        return f"{self._token.token_type} {token}"

    def handle_401(self) -> str:
        """Re-authenticate once after an API 401."""
        _log.warning("got_401_refreshing_token")
        self._fetch_token()
        assert self._token is not None
        return self._token.value

    def handle_401_authorization(self) -> str:
        """Re-authenticate once and return the new REST authorization value."""
        self.handle_401()
        assert self._token is not None
        return f"{self._token.token_type} {self._token.value}"

    def _response_message(self, response: httpx.Response) -> str:
        """Extract a server error message without echoing credential fields."""
        try:
            payload = response.json()
        except ValueError:
            return "Non-JSON response from token endpoint."
        if not isinstance(payload, dict):
            return "Unexpected error response from token endpoint."
        messages = [
            payload[key]
            for key in ("messages", "message", "error_description", "error")
            if payload.get(key)
        ]
        # Only render strings: never stringify an object that might contain a token.
        parts: list[str] = []
        for message in messages:
            if isinstance(message, str):
                parts.append(message)
            elif isinstance(message, list):
                parts.extend(part for part in message if isinstance(part, str))
        text = "; ".join(parts) or "Token endpoint rejected the request."
        sensitive = [
            self._settings.trading_id,
            self._settings.api_key.get_secret_value(),
        ]
        for section in (payload, payload.get("data")):
            if isinstance(section, dict):
                sensitive.extend(
                    value
                    for key in (
                        "accessToken",
                        "client_token",
                        "access_token",
                        "token",
                        "secret",
                    )
                    if isinstance(value := section.get(key), str) and value
                )
        if self._token is not None:
            sensitive.append(self._token.value)
        for value in sorted(sensitive, key=len, reverse=True):
            text = text.replace(value, "[REDACTED]")
        return re.sub(
            r"\b[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
            "[REDACTED]",
            text,
        )

    def _fetch_token(self) -> None:
        _log.info("fetching_token")
        try:
            response = self._http.post(
                _TOKEN_URL,
                json={
                    "tradingId": self._settings.trading_id,
                    "secret": self._settings.api_key.get_secret_value(),
                },
                headers={**build_default_headers(self._settings), "Accept": "application/json"},
                auth=httpx.Auth(),  # Token requests must not invoke REST authentication.
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise AuthError(f"Failed to reach token endpoint ({type(exc).__name__}).") from None
        if not response.is_success:
            error_type = InvalidCredentials if response.status_code == 401 else AuthError
            raise error_type(
                f"Token request failed with HTTP {response.status_code}: "
                f"{self._response_message(response)}",
                status_code=response.status_code,
            )
        token = _parse_token_response(response)
        self._token = token
        _log.info("token_acquired")
