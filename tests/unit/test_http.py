"""Unit tests for the HTTP layer."""

from __future__ import annotations

import ssl

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
    _PINNED_CERT_PATH,
    _build_ssl_context,
    build_default_headers,
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
        s = Settings(partner_id="p", partner_secret="s", trading_uuid="u")
        headers = build_default_headers(s)
        assert "Accept-Language" in headers
        assert "X-Server-Select" in headers
        assert "x-company-code" in headers
        assert "x-api-version" in headers
        assert "User-Agent" in headers

    def test_simulation_sets_server_select(self) -> None:
        s = Settings(partner_id="p", partner_secret="s", trading_uuid="u", simulation=True)
        headers = build_default_headers(s)
        assert headers["X-Server-Select"] == "simulation"

    def test_real_sets_server_select(self) -> None:
        s = Settings(partner_id="p", partner_secret="s", trading_uuid="u", simulation=False)
        headers = build_default_headers(s)
        assert headers["X-Server-Select"] == "real"

    def test_user_agent_contains_package_name(self) -> None:
        s = Settings(partner_id="p", partner_secret="s", trading_uuid="u")
        headers = build_default_headers(s)
        assert "younit-python" in headers["User-Agent"]


class TestBuildSslContext:
    """SSL verification must stay ON via a pinned cert, never disabled outright."""

    def test_ssl_verify_and_http2_are_not_settings_fields(self) -> None:
        assert "ssl_verify" not in Settings.model_fields
        assert "http2" not in Settings.model_fields

    def test_pinned_cert_file_exists(self) -> None:
        assert _PINNED_CERT_PATH.is_file()
        assert "BEGIN CERTIFICATE" in _PINNED_CERT_PATH.read_text()

    def test_context_requires_verification(self) -> None:
        ctx = _build_ssl_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
        assert ctx.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
