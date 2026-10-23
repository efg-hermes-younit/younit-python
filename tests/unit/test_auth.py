"""Unit tests for public-key authentication and token lifecycle."""

from __future__ import annotations

import json

import conftest as conf
import httpx
import pytest

from younit.auth import IdentityProvider, InMemoryTokenStore, _TokenRecord
from younit.exceptions import AuthError, InvalidCredentials


class TestTokenRecord:
    def test_not_expired(self):
        record = _TokenRecord("tok", expires_in=86400, token_type="Bearer")
        assert not record.is_expired()
        assert not record.needs_refresh()

    def test_expired(self):
        record = _TokenRecord("tok", expires_in=-1, token_type="Bearer")
        assert record.is_expired()
        assert record.needs_refresh()

    def test_needs_refresh_at_5_min(self):
        record = _TokenRecord("tok", expires_in=299, token_type="Bearer")
        assert record.needs_refresh()
        assert not record.is_expired()

    def test_no_refresh_needed(self):
        assert not _TokenRecord("tok", expires_in=600, token_type="Bearer").needs_refresh()


class TestInMemoryTokenStore:
    def test_get_missing(self):
        assert InMemoryTokenStore().get("key") is None

    def test_set_and_get(self):
        store = InMemoryTokenStore()
        store.set("token", "value123")
        assert store.get("token") == "value123"

    def test_overwrite(self):
        store = InMemoryTokenStore()
        store.set("token", "old")
        store.set("token", "new")
        assert store.get("token") == "new"


class TestIdentityProvider:
    @pytest.mark.parametrize("wrapped", [False, True])
    def test_authenticate_success(self, respx_mock, mock_http, settings, wrapped):
        payload = conf.CLIENT_TOKEN_RESPONSE
        route = respx_mock.post(conf.TOKEN_URL).respond(
            200, json={"data": payload, "messages": None} if wrapped else payload
        )
        provider = IdentityProvider(settings, mock_http)
        provider.authenticate()
        assert provider.get_token() == conf.FAKE_CLIENT_TOKEN
        assert provider.get_authorization() == f"Bearer {conf.FAKE_CLIENT_TOKEN}"
        assert route.call_count == 1
        request = route.calls.last.request
        assert json.loads(request.content) == {
            "tradingId": conf.FAKE_TRADING_ID,
            "secret": conf.FAKE_API_KEY,
        }
        assert request.headers["content-type"] == "application/json"
        assert "Authorization" not in request.headers

    @pytest.mark.parametrize("status", [400, 401, 403, 500])
    def test_failure_includes_status_and_message(self, respx_mock, mock_http, settings, status):
        route = respx_mock.post(conf.TOKEN_URL).respond(
            status, json={"messages": ["Credentials rejected"]}
        )
        provider = IdentityProvider(settings, mock_http)
        error = InvalidCredentials if status == 401 else AuthError
        with pytest.raises(error, match=f"HTTP {status}: Credentials rejected"):
            provider.authenticate()
        assert route.call_count == 1

    def test_error_redacts_echoed_credentials_and_tokens(self, respx_mock, mock_http, settings):
        respx_mock.post(conf.TOKEN_URL).respond(
            401,
            json={
                "message": (
                    f"Rejected {conf.FAKE_API_KEY} for {conf.FAKE_TRADING_ID}: must-not-be-shown"
                ),
                "error_description": "Bearer abc.def.ghi",
                "data": {"accessToken": "must-not-be-shown"},
            },
        )
        with pytest.raises(InvalidCredentials) as caught:
            IdentityProvider(settings, mock_http).authenticate()
        for value in (conf.FAKE_API_KEY, conf.FAKE_TRADING_ID, "abc.def.ghi", "must-not-be-shown"):
            assert value not in str(caught.value)

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            [],
            {"expiresIn": 86400, "tokenType": "Bearer"},
            {"accessToken": 123, "expiresIn": 86400, "tokenType": "Bearer"},
            {"accessToken": "tok", "tokenType": "Bearer"},
            {"accessToken": "tok", "expiresIn": True, "tokenType": "Bearer"},
            {"accessToken": "tok", "expiresIn": "86400", "tokenType": "Bearer"},
            {"accessToken": "tok", "expiresIn": 0, "tokenType": "Bearer"},
            {"accessToken": "tok", "expiresIn": 86400},
            {"accessToken": "tok", "expiresIn": 86400, "tokenType": 123},
        ],
    )
    def test_invalid_token_response_raises(self, respx_mock, mock_http, settings, payload):
        respx_mock.post(conf.TOKEN_URL).respond(200, json=payload)
        with pytest.raises(AuthError):
            IdentityProvider(settings, mock_http).authenticate()

    def test_missing_token_lists_top_level_keys_only(self, respx_mock, mock_http, settings):
        respx_mock.post(conf.TOKEN_URL).respond(
            200,
            json={
                "messages": None,
                "data": {"expiresIn": 86400, "tokenType": "Bearer"},
            },
        )
        with pytest.raises(AuthError) as caught:
            IdentityProvider(settings, mock_http).authenticate()
        assert str(caught.value) == (
            "Token response missing or invalid 'accessToken'; "
            "top-level keys received: ['data', 'messages']."
        )

    @pytest.mark.parametrize("status", [200, 502])
    def test_html_response_raises_safe_error(self, respx_mock, mock_http, settings, status):
        respx_mock.post(conf.TOKEN_URL).respond(
            status,
            text=f"<html>{conf.FAKE_API_KEY}</html>",
            headers={"content-type": "text/html"},
        )
        with pytest.raises(AuthError, match=f"HTTP {status}") as caught:
            IdentityProvider(settings, mock_http).authenticate()
        assert conf.FAKE_API_KEY not in str(caught.value)

    def test_network_failure_does_not_echo_credentials(self, respx_mock, mock_http, settings):
        respx_mock.post(conf.TOKEN_URL).mock(
            side_effect=httpx.ConnectError(f"failure {conf.FAKE_API_KEY}")
        )
        with pytest.raises(AuthError, match="ConnectError") as caught:
            IdentityProvider(settings, mock_http).authenticate()
        assert conf.FAKE_API_KEY not in str(caught.value)

    @pytest.mark.parametrize("seconds_left", [-1, 299])
    def test_expired_or_expiring_token_refreshes(
        self, respx_mock, mock_http, settings, seconds_left
    ):
        route = respx_mock.post(conf.TOKEN_URL).respond(200, json=conf.CLIENT_TOKEN_RESPONSE)
        provider = IdentityProvider(settings, mock_http)
        provider._token = _TokenRecord("old-token", expires_in=seconds_left, token_type="Bearer")
        assert provider.get_token() == conf.FAKE_CLIENT_TOKEN
        assert route.call_count == 1

    def test_handle_401_refreshes_token(self, respx_mock, mock_http, settings):
        route = respx_mock.post(conf.TOKEN_URL).respond(200, json=conf.CLIENT_TOKEN_RESPONSE)
        provider = IdentityProvider(settings, mock_http)
        assert provider.handle_401() == conf.FAKE_CLIENT_TOKEN
        assert route.call_count == 1

    def test_refresh_failure_is_not_hidden(self, respx_mock, mock_http, settings):
        respx_mock.post(conf.TOKEN_URL).respond(503, json={"message": "Unavailable"})
        provider = IdentityProvider(settings, mock_http)
        provider._token = _TokenRecord("expired", expires_in=-1, token_type="Bearer")
        with pytest.raises(AuthError, match="HTTP 503: Unavailable"):
            provider.get_token()
