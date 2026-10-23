"""Unit tests for the HTTP layer."""

from __future__ import annotations

import httpx
import pytest
import respx

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
from younit.http import (
    _should_retry,
    build_default_headers,
    build_httpx_client,
    execute_with_retry,
    raise_for_status,
    timed_request,
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

    def test_lowercase_request_id_header_extracted(self) -> None:
        response = httpx.Response(500, json={}, headers={"x-request-id": "req-lower"})
        with pytest.raises(ServerError) as exc_info:
            raise_for_status(response)
        assert exc_info.value.request_id == "req-lower"

    def test_malformed_json_body_falls_back_to_default_message(self) -> None:
        response = httpx.Response(400, text="not json at all")
        with pytest.raises(BadRequest) as exc_info:
            raise_for_status(response)
        assert exc_info.value.message == "HTTP 400"

    def test_non_dict_json_body_falls_back_to_default_message(self) -> None:
        response = httpx.Response(400, json=["unexpected", "list"])
        with pytest.raises(BadRequest) as exc_info:
            raise_for_status(response)
        assert exc_info.value.message == "HTTP 400"

    def test_unmapped_status_raises_generic_api_error(self) -> None:
        response = httpx.Response(409, json={})
        with pytest.raises(APIError) as exc_info:
            raise_for_status(response)
        assert exc_info.value.status_code == 409
        assert not isinstance(exc_info.value, BadRequest)


class TestShouldRetry:
    """Unit tests for the internal retry-eligibility predicate."""

    def test_false_when_max_retries_reached(self) -> None:
        assert _should_retry("GET", "/api/v1/stocks", 3, None, 500) is False

    def test_false_for_non_idempotent_method(self) -> None:
        assert _should_retry("POST", "/api/v1/stocks", 0, None, 500) is False

    def test_false_for_order_placement_path_even_if_idempotent_status(self) -> None:
        assert _should_retry("GET", "/api/v1/orders/normal", 0, None, 500) is False

    def test_true_on_connect_error(self) -> None:
        exc = httpx.ConnectError("boom")
        assert _should_retry("GET", "/api/v1/stocks", 0, exc, None) is True

    def test_true_on_read_timeout(self) -> None:
        exc = httpx.ReadTimeout("boom")
        assert _should_retry("GET", "/api/v1/stocks", 0, exc, None) is True

    def test_true_on_5xx_status(self) -> None:
        assert _should_retry("GET", "/api/v1/stocks", 0, None, 503) is True

    def test_false_on_4xx_status(self) -> None:
        assert _should_retry("GET", "/api/v1/stocks", 0, None, 404) is False

    def test_false_when_no_exception_or_retryable_status(self) -> None:
        assert _should_retry("GET", "/api/v1/stocks", 0, None, 200) is False


class TestTimedRequest:
    def test_yields_duration_ms(self) -> None:
        with timed_request("GET", "/api/v1/stocks") as info:
            pass
        assert "duration_ms" in info
        assert info["duration_ms"] >= 0


class TestBuildHttpxClient:
    def test_returns_configured_client(self) -> None:
        s = Settings(trading_id="p", api_key="s")
        client = build_httpx_client(s)
        try:
            assert isinstance(client, httpx.Client)
            assert client.follow_redirects is True
        finally:
            client.close()


class TestExecuteWithRetry:
    """Unit tests for the retry-wrapped request executor."""

    def test_success_on_first_attempt(self, respx_mock: respx.MockRouter) -> None:
        respx_mock.get("https://api.test/api/v1/stocks").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        with httpx.Client() as http:
            response = execute_with_retry(
                http,
                "GET",
                "https://api.test/api/v1/stocks",
                "/api/v1/stocks",
                token_getter=lambda: "tok",
                default_headers={},
            )
        assert response.status_code == 200

    def test_retries_on_5xx_then_succeeds(self, respx_mock: respx.MockRouter) -> None:
        route = respx_mock.get("https://api.test/api/v1/stocks")
        route.side_effect = [
            httpx.Response(500, json={}),
            httpx.Response(200, json={"ok": True}),
        ]
        with httpx.Client() as http:
            response = execute_with_retry(
                http,
                "GET",
                "https://api.test/api/v1/stocks",
                "/api/v1/stocks",
                token_getter=lambda: "tok",
                default_headers={},
            )
        assert response.status_code == 200
        assert route.call_count == 2

    def test_returns_last_response_after_exhausting_retries(
        self, respx_mock: respx.MockRouter
    ) -> None:
        route = respx_mock.get("https://api.test/api/v1/stocks")
        route.mock(return_value=httpx.Response(500, json={}))
        with httpx.Client() as http:
            response = execute_with_retry(
                http,
                "GET",
                "https://api.test/api/v1/stocks",
                "/api/v1/stocks",
                token_getter=lambda: "tok",
                default_headers={},
            )
        assert response.status_code == 500
        assert route.call_count == 4  # initial attempt + 3 retries

    def test_post_to_order_path_never_retried(self, respx_mock: respx.MockRouter) -> None:
        route = respx_mock.post("https://api.test/api/v1/orders/normal")
        route.mock(return_value=httpx.Response(500, json={}))
        with httpx.Client() as http:
            response = execute_with_retry(
                http,
                "POST",
                "https://api.test/api/v1/orders/normal",
                "/api/v1/orders/normal",
                token_getter=lambda: "tok",
                default_headers={},
            )
        assert response.status_code == 500
        assert route.call_count == 1

    def test_connect_error_retried_then_raises_when_exhausted(
        self, respx_mock: respx.MockRouter
    ) -> None:
        route = respx_mock.get("https://api.test/api/v1/stocks")
        route.mock(side_effect=httpx.ConnectError("boom"))
        with httpx.Client() as http, pytest.raises(httpx.ConnectError):
            execute_with_retry(
                http,
                "GET",
                "https://api.test/api/v1/stocks",
                "/api/v1/stocks",
                token_getter=lambda: "tok",
                default_headers={},
            )
        assert route.call_count == 4

    def test_per_call_headers_are_merged(self, respx_mock: respx.MockRouter) -> None:
        route = respx_mock.get("https://api.test/api/v1/stocks").mock(
            return_value=httpx.Response(200, json={})
        )
        with httpx.Client() as http:
            execute_with_retry(
                http,
                "GET",
                "https://api.test/api/v1/stocks",
                "/api/v1/stocks",
                token_getter=lambda: "tok",
                default_headers={"X-Default": "1"},
                headers={"X-Extra": "2"},
            )
        sent = route.calls.last.request.headers
        assert sent["X-Default"] == "1"
        assert sent["X-Extra"] == "2"
        assert sent["Authorization"] == "Bearer tok"


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
