"""Unit tests for authentication and token lifecycle."""

from __future__ import annotations

import conftest as conf
import httpx
import pytest

import younit.config
from younit.auth import IdentityProvider, InMemoryTokenStore, _TokenRecord
from younit.exceptions import AuthError, InvalidCredentials

FAKE_BASE_URL = conf.FAKE_BASE_URL
SERVER_TOKEN_RESPONSE = conf.SERVER_TOKEN_RESPONSE
CLIENT_TOKEN_RESPONSE = conf.CLIENT_TOKEN_RESPONSE
FAKE_CLIENT_TOKEN = conf.FAKE_CLIENT_TOKEN


def _make_settings(**kwargs):
    return younit.config.Settings(
        partner_id=conf.FAKE_PARTNER_ID,
        partner_secret=conf.FAKE_PARTNER_SECRET,
        trading_uuid=conf.FAKE_TRADING_UUID,
        identity_url=FAKE_BASE_URL,
        **kwargs,
    )


class TestTokenRecord:
    def test_not_expired(self):
        r = _TokenRecord("tok", expires_in=86400)
        assert not r.is_expired()
        assert not r.needs_refresh()

    def test_expired(self):
        r = _TokenRecord("tok", expires_in=-1)
        assert r.is_expired()
        assert r.needs_refresh()

    def test_needs_refresh_at_5_min(self):
        r = _TokenRecord("tok", expires_in=299)
        assert r.needs_refresh()
        assert not r.is_expired()

    def test_no_refresh_needed(self):
        r = _TokenRecord("tok", expires_in=600)
        assert not r.needs_refresh()


class TestInMemoryTokenStore:
    def test_get_missing(self):
        s = InMemoryTokenStore()
        assert s.get("key") is None

    def test_set_and_get(self):
        s = InMemoryTokenStore()
        s.set("token", "value123")
        assert s.get("token") == "value123"

    def test_overwrite(self):
        s = InMemoryTokenStore()
        s.set("token", "old")
        s.set("token", "new")
        assert s.get("token") == "new"


class TestIdentityProvider:
    def test_authenticate_success(self, respx_mock, mock_http):
        respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
            return_value=httpx.Response(200, json=SERVER_TOKEN_RESPONSE)
        )
        respx_mock.post(f"{FAKE_BASE_URL}/connect/iframe-access").mock(
            return_value=httpx.Response(200, json=CLIENT_TOKEN_RESPONSE)
        )
        provider = IdentityProvider(_make_settings(), mock_http)
        provider.authenticate()
        assert provider.get_client_token() == FAKE_CLIENT_TOKEN

    def test_invalid_credentials_raises(self, respx_mock, mock_http):
        respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )
        s = younit.config.Settings(
            partner_id="bad",
            partner_secret="bad",
            trading_uuid=conf.FAKE_TRADING_UUID,
            identity_url=FAKE_BASE_URL,
        )
        provider = IdentityProvider(s, mock_http)
        with pytest.raises(InvalidCredentials):
            provider.authenticate()

    def test_server_error_raises_auth_error(self, respx_mock, mock_http):
        respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
            return_value=httpx.Response(500, json={})
        )
        provider = IdentityProvider(_make_settings(), mock_http)
        with pytest.raises(AuthError):
            provider.authenticate()

    def test_missing_access_token_raises(self, respx_mock, mock_http):
        respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
            return_value=httpx.Response(200, json={"expires_in": 86400})
        )
        provider = IdentityProvider(_make_settings(), mock_http)
        with pytest.raises(AuthError):
            provider.authenticate()

    def test_handle_401_refreshes_token(self, respx_mock, mock_http):
        respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
            return_value=httpx.Response(200, json=SERVER_TOKEN_RESPONSE)
        )
        respx_mock.post(f"{FAKE_BASE_URL}/connect/iframe-access").mock(
            return_value=httpx.Response(200, json=CLIENT_TOKEN_RESPONSE)
        )
        provider = IdentityProvider(_make_settings(), mock_http)
        provider.authenticate()
        new_token = provider.handle_401()
        assert new_token == FAKE_CLIENT_TOKEN
