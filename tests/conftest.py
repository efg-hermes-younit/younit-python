"""Shared test fixtures and configuration for the younit test suite.

Unit tests in tests/unit/ use respx to mock all HTTP traffic.
No real API calls are made in unit tests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from younit.config import Settings

# ---------------------------------------------------------------------------
# Constants / canned response data
# ---------------------------------------------------------------------------

FAKE_SERVER_TOKEN = "fake-server-jwt-token"
FAKE_CLIENT_TOKEN = "fake-client-jwt-token"
FAKE_PARTNER_ID = "test-partner-id"
FAKE_PARTNER_SECRET = "test-partner-secret"
FAKE_TRADING_UUID = "test-trading-uuid"
FAKE_BASE_URL = "https://api.efg-one.test"

SERVER_TOKEN_RESPONSE = {
    "access_token": FAKE_SERVER_TOKEN,
    "token_type": "Bearer",
    "expires_in": 86400,
    "scope": "trading.read trading.write",
}

CLIENT_TOKEN_RESPONSE = {
    "iframe_url": f"{FAKE_BASE_URL}/?token={FAKE_CLIENT_TOKEN}",
    "client_token": FAKE_CLIENT_TOKEN,
    "token_type": "Bearer",
    "expires_in": 86400,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Minimal Settings instance for testing."""
    return Settings(
        partner_id=FAKE_PARTNER_ID,
        partner_secret=FAKE_PARTNER_SECRET,
        trading_uuid=FAKE_TRADING_UUID,
        identity_url=FAKE_BASE_URL,
        simulation=True,
    )


@pytest.fixture
def mock_http() -> httpx.Client:
    """A real httpx.Client instance for use in mocked tests."""
    return httpx.Client()


@pytest.fixture
def auth_routes(respx_mock: respx.MockRouter) -> respx.MockRouter:
    """Pre-configure auth endpoints on the respx mock router."""
    respx_mock.post(f"{FAKE_BASE_URL}/connect/token").mock(
        return_value=httpx.Response(200, json=SERVER_TOKEN_RESPONSE)
    )
    respx_mock.post(f"{FAKE_BASE_URL}/connect/iframe-access").mock(
        return_value=httpx.Response(200, json=CLIENT_TOKEN_RESPONSE)
    )
    return respx_mock
