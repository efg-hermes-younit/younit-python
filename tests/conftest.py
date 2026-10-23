"""Shared test fixtures and configuration for the younit test suite.

Unit tests in tests/unit/ use respx to mock all HTTP traffic.
No real API calls are made in unit tests.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from younit.config import _TOKEN_URL, Settings

# ---------------------------------------------------------------------------
# Constants / canned response data
# ---------------------------------------------------------------------------

FAKE_CLIENT_TOKEN = "fake-client-jwt-token"
FAKE_API_KEY = "test-api-key"
FAKE_TRADING_ID = "test-trading-id"
FAKE_BASE_URL = "https://api.efg-one.test"
TOKEN_URL = _TOKEN_URL

CLIENT_TOKEN_RESPONSE = {
    "accessToken": FAKE_CLIENT_TOKEN,
    "tokenType": "Bearer",
    "expiresIn": 86400,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    """Minimal Settings instance for testing."""
    return Settings(
        trading_id=FAKE_TRADING_ID,
        api_key=FAKE_API_KEY,
        simulation=True,
    )


@pytest.fixture
def mock_http() -> httpx.Client:
    """A real httpx.Client instance for use in mocked tests."""
    return httpx.Client()


@pytest.fixture
def auth_routes(respx_mock: respx.MockRouter) -> respx.MockRouter:
    """Pre-configure auth endpoints on the respx mock router."""
    respx_mock.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=CLIENT_TOKEN_RESPONSE))
    return respx_mock
