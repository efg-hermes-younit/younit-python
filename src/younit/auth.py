"""Authentication and token lifecycle management for the Younit API SDK.

Implements the two-step partner authentication flow documented in the
partner integration guide:

1. ``POST /connect/token`` — exchange partner credentials for a server token
2. ``POST /connect/iframe-access`` — exchange server token for a client token
   scoped to a specific trading UUID

Token storage is pluggable via the :class:`TokenStore` protocol. The default
implementation is :class:`InMemoryTokenStore`.

Proactive refresh: tokens are refreshed 5 minutes before expiry.
Reactive refresh: a 401 response triggers a single refresh-and-retry.
Token lifetimes are always read from ``expires_in`` in the response — never hardcoded.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import httpx

from younit.config import Settings
from younit.exceptions import AuthError, InvalidCredentials, TokenExpired
from younit.logging import get_logger

_log = get_logger(__name__)

# How many seconds before expiry to proactively refresh
_REFRESH_BUFFER_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Token store protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenStore(Protocol):
    """Protocol for pluggable token storage.

    Implement this to store tokens in Redis, a database, or any other
    durable store. The default :class:`InMemoryTokenStore` keeps tokens
    in memory for the lifetime of the Client.
    """

    def get(self, key: str) -> str | None:
        """Retrieve a token value by key. Returns None if not found."""
        ...

    def set(self, key: str, value: str) -> None:
        """Store a token value."""
        ...


class InMemoryTokenStore:
    """Default token store: keeps tokens in memory.

    Tokens do not persist across process restarts. Suitable for
    short-lived scripts and single-process applications.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Retrieve a token by key."""
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        """Store a token."""
        self._store[key] = value


# ---------------------------------------------------------------------------
# Token record
# ---------------------------------------------------------------------------


class _TokenRecord:
    """Holds a token value with its expiry timestamp."""

    __slots__ = ("expires_at", "value")

    def __init__(self, value: str, expires_in: int) -> None:
        self.value = value
        # expires_in is seconds from now; we store the absolute expiry timestamp
        self.expires_at = time.monotonic() + expires_in

    def is_expired(self) -> bool:
        """Return True if the token has expired."""
        return time.monotonic() >= self.expires_at

    def needs_refresh(self) -> bool:
        """Return True if the token should be proactively refreshed."""
        return time.monotonic() >= (self.expires_at - _REFRESH_BUFFER_SECONDS)


# ---------------------------------------------------------------------------
# Identity provider
# ---------------------------------------------------------------------------


class IdentityProvider:
    """Manages the full partner→client token lifecycle.

    Users of the SDK never interact with this class directly.
    The :class:`~younit.client.Client` constructs and owns one instance.

    Token flow:
    1. Fetch server token via ``POST /connect/token``
    2. Fetch client token via ``POST /connect/iframe-access``
    3. Proactively refresh the client token 5 minutes before expiry
    4. On 401, refresh once and retry; raise :class:`~younit.exceptions.AuthError`
       if the refresh also fails

    Token lifetimes are always read from ``expires_in`` in the response.
    Never hardcoded.
    """

    def __init__(
        self,
        settings: Settings,
        http: httpx.Client,
        store: TokenStore | None = None,
    ) -> None:
        self._settings = settings
        self._http = http
        self._store = store or InMemoryTokenStore()

        self._server_token: _TokenRecord | None = None
        self._client_token: _TokenRecord | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def authenticate(self) -> None:
        """Perform the full two-step authentication flow.

        Called automatically on :class:`~younit.client.Client` construction.

        Raises:
            InvalidCredentials: If the partner credentials are rejected.
            AuthError: On any other authentication failure.
        """
        try:
            self._fetch_server_token()
        except (AuthError, KeyboardInterrupt) as exc:
            # On Windows, the SSL handshake can be interrupted by a queued SIGINT
            # (e.g. during debugger attachment). Retry once after a short pause.
            _log.debug("auth_connect_retry", reason=type(exc).__name__)
            time.sleep(0.2)
            self._fetch_server_token()
        self._fetch_client_token()

    def get_client_token(self) -> str:
        """Return a valid client token, refreshing proactively if needed.

        Returns:
            The current client bearer token string.

        Raises:
            TokenExpired: If the token cannot be refreshed.
            AuthError: On authentication failure.
        """
        if self._client_token is None or self._client_token.needs_refresh():
            _log.info("proactive_token_refresh", reason="expiry_approaching")
            self._refresh_client_token()
        elif self._client_token.is_expired():
            _log.warning("client_token_expired", action="refreshing")
            self._refresh_client_token()

        if self._client_token is None or self._client_token.is_expired():
            raise TokenExpired("Client token expired and could not be refreshed.")

        return self._client_token.value

    def handle_401(self) -> str:
        """Handle a 401 response by refreshing the client token once.

        Returns:
            The new client bearer token string.

        Raises:
            AuthError: If the refresh attempt also fails.
        """
        _log.warning("got_401_refreshing_token")
        try:
            self._refresh_client_token()
        except AuthError:
            raise
        except Exception as exc:
            raise AuthError(f"Token refresh after 401 failed: {exc}") from exc

        if self._client_token is None:
            raise AuthError("Token refresh after 401 produced no token.")

        return self._client_token.value

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _fetch_server_token(self) -> None:
        """Fetch the server-to-server token from POST /connect/token."""
        url = f"{self._settings.identity_url}/connect/token"
        data = {
            "grant_type": "partner_credentials",
            "partner_id": self._settings.partner_id,
            "partner_secret": self._settings.partner_secret,
            "scope": self._settings.scope_string,
        }

        _log.info("fetching_server_token", url=url, scope=self._settings.scope_string)

        try:
            response = self._http.post(
                url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except Exception as exc:
            raise AuthError(f"Failed to reach identity provider: {exc}") from exc

        if response.status_code == 401:
            raise InvalidCredentials(
                "Partner credentials rejected by the identity provider. "
                "Verify EFG_PARTNER_ID and EFG_PARTNER_SECRET."
            )

        if not response.is_success:
            raise AuthError(
                f"Server token request failed with HTTP {response.status_code}: {response.text}"
            )

        content_type = response.headers.get("content-type", "")
        if "json" not in content_type:
            raise AuthError(
                f"Server token request returned unexpected content-type '{content_type}' "
                f"(HTTP {response.status_code}). "
                "This is typically caused by a firewall or proxy blocking the request. "
                f"Response: {response.text[:300]!r}"
            )

        payload = response.json()
        # API wraps responses in {"messages": ..., "data": {...}}
        payload = payload.get("data") or payload
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")

        if not token:
            raise AuthError("Server token response missing 'access_token'.")
        if not isinstance(expires_in, int):
            raise AuthError("Server token response missing or invalid 'expires_in'.")

        self._server_token = _TokenRecord(token, expires_in)
        _log.info("server_token_acquired", expires_in_seconds=expires_in)

    def _fetch_client_token(self) -> None:
        """Fetch the client-scoped token from POST /connect/iframe-access."""
        if self._server_token is None or self._server_token.is_expired():
            _log.info("server_token_expired_or_missing", action="refetching")
            self._fetch_server_token()

        if self._server_token is None:
            raise AuthError("Server token unavailable after fetch attempt.")

        url = f"{self._settings.identity_url}/connect/iframe-access"

        _log.info(
            "fetching_client_token",
            url=url,
            # trading_uuid intentionally not logged — treat as semi-sensitive
        )

        try:
            response = self._http.post(
                url,
                json={"tradingUuid": self._settings.trading_uuid},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._server_token.value}",
                },
            )
        except Exception as exc:
            raise AuthError(f"Failed to fetch client token: {exc}") from exc

        if response.status_code == 401:
            raise InvalidCredentials(
                "Server token was rejected by /connect/iframe-access. "
                "The server token may have expired."
            )

        if not response.is_success:
            raise AuthError(
                f"Client token request failed with HTTP {response.status_code}: {response.text}"
            )

        payload = response.json()
        # API wraps responses in {"messages": ..., "data": {...}}
        payload = payload.get("data") or payload
        token = payload.get("client_token")
        expires_in = payload.get("expires_in")

        if not token:
            raise AuthError("Client token response missing 'client_token'.")
        if not isinstance(expires_in, int):
            raise AuthError("Client token response missing or invalid 'expires_in'.")

        self._client_token = _TokenRecord(token, expires_in)
        _log.info("client_token_acquired", expires_in_seconds=expires_in)

    def _refresh_client_token(self) -> None:
        """Refresh the client token, re-fetching the server token if needed."""
        if self._server_token is None or self._server_token.needs_refresh():
            self._fetch_server_token()
        self._fetch_client_token()
