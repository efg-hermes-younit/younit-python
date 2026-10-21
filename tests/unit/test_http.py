"""Unit tests for the HTTP layer."""

from __future__ import annotations

import httpx
import pytest

from younit.config import Settings
from younit.exceptions import (
    BadRequest,
    Forbidden,
    NotFound,
    RateLimited,
    ServerError,
    Unauthorized,
)
from younit.http import (
    build_default_headers,
    build_httpx_client,
    raise_for_status,
)


class TestRaiseForStatus:
    """Test HTTP error → exception mapping."""

    def test_200_does_not_raise(self) -> None:
        response = httpx.Response(200, json={"data": True})
        raise_for_status(response)  # Should not raise

    def test_201_does_not_raise(self) -> None:
        response = httpx.Response(201, json={})
        raise_for_status(response)

    def test_400_raises_bad_request(self) -> None:
        response = httpx.Response(400, json={"messages": ["Invalid parameter"]})
        with pytest.raises(BadRequest) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 400

    def test_401_raises_unauthorized(self) -> None:
        response = httpx.Response(401, json={})
        with pytest.raises(Unauthorized) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 401

    def test_403_raises_forbidden(self) -> None:
        response = httpx.Response(403, json={})
        with pytest.raises(Forbidden) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 403

    def test_404_raises_not_found(self) -> None:
        response = httpx.Response(404, json={})
        with pytest.raises(NotFound) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 404

    def test_429_raises_rate_limited(self) -> None:
        response = httpx.Response(429, json={})
        with pytest.raises(RateLimited) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 429

    def test_500_raises_server_error(self) -> None:
        response = httpx.Response(500, json={})
        with pytest.raises(ServerError) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 500

    def test_503_raises_server_error(self) -> None:
        response = httpx.Response(503, text="Service unavailable")
        with pytest.raises(ServerError) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 503

    def test_error_messages_extracted(self) -> None:
        response = httpx.Response(
            400, json={"messages": ["Price out of range", "Quantity too small"], "status": 2}
        )
        with pytest.raises(BadRequest) as exc_info:
            raise_for_status(response)
        assert "Price out of range" in exc_info.value.message

    def test_request_id_extracted(self) -> None:
        response = httpx.Response(500, json={}, headers={"X-Request-Id": "req-xyz-123"})
        with pytest.raises(ServerError) as exc_info:
            raise_for_status(response)
        assert exc_info.value.request_id == "req-xyz-123"


class TestBuildDefaultHeaders:
    def test_headers_include_required_fields(self) -> None:
        s = Settings(trading_id="test-id", api_key="test-key")
        headers = build_default_headers(s)
        assert "Accept-Language" in headers
        assert "X-Server-Select" in headers
        assert "x-company-code" in headers
        assert "x-api-version" in headers
        assert "User-Agent" in headers

    def test_simulation_sets_server_select(self) -> None:
        s = Settings(trading_id="test-id", api_key="test-key", simulation=True)
        headers = build_default_headers(s)
        assert headers["X-Server-Select"] == "simulation"

    def test_real_sets_server_select(self) -> None:
        s = Settings(trading_id="test-id", api_key="test-key", simulation=False)
        headers = build_default_headers(s)
        assert headers["X-Server-Select"] == "real"

    def test_user_agent_contains_package_name(self) -> None:
        s = Settings(trading_id="test-id", api_key="test-key")
        headers = build_default_headers(s)
        assert "younit-python" in headers["User-Agent"]


class TestBuildSslContext:
    """Standard TLS verification (no cert pinning) is used unconditionally."""

    def test_ssl_verify_and_http2_are_not_settings_fields(self) -> None:
        assert "ssl_verify" not in Settings.model_fields
        assert "http2" not in Settings.model_fields

    def test_build_httpx_client_constructs_successfully(self) -> None:
        """No pinned cert / custom SSL context is required — httpx's own
        default (system CA trust store) is used, i.e. standard verification."""
        s = Settings(trading_id="test-id", api_key="test-key")
        client = build_httpx_client(s)
        try:
            assert isinstance(client, httpx.Client)
        finally:
            client.close()

    def test_no_pinning_symbols_remain(self) -> None:
        """Regression guard: cert pinning was removed 2026-09-13; these
        symbols should not reappear without deliberately updating this test."""
        import younit.http as http_module

        assert not hasattr(http_module, "_build_ssl_context")
        assert not hasattr(http_module, "_PINNED_CERT_PATH")
