"""Unit tests for config, exceptions, and enums."""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from younit import config
from younit.config import Settings
from younit.enums import (
    ExecutionInstruction,
    OperationType,
    OrderCategory,
    OrderExpireTerm,
    OrderVia,
)
from younit.exceptions import (
    APIError,
    AuthError,
    BadRequest,
    ConfigError,
    EFGError,
    Forbidden,
    InsufficientFunds,
    InvalidCredentials,
    InvalidOrder,
    InvalidSymbol,
    NotFound,
    OrderError,
    OrderRejected,
    RateLimited,
    ServerError,
    TokenExpired,
    Unauthorized,
)


class TestExceptionHierarchy:
    """Verify the exception hierarchy is correct."""

    def test_efg_error_is_base(self) -> None:
        exc = EFGError("test")
        assert isinstance(exc, Exception)
        assert str(exc) == "test"

    def test_auth_error_hierarchy(self) -> None:
        for cls in (AuthError, InvalidCredentials, TokenExpired):
            exc = cls("msg")
            assert isinstance(exc, EFGError)
            assert isinstance(exc, AuthError)

    def test_api_error_has_context(self) -> None:
        exc = APIError(
            "HTTP 404", status_code=404, response_body='{"msg": "not found"}', request_id="req-123"
        )
        assert exc.status_code == 404
        assert exc.response_body == '{"msg": "not found"}'
        assert exc.request_id == "req-123"

    def test_api_error_subclasses(self) -> None:
        for cls in (BadRequest, Unauthorized, Forbidden, NotFound, RateLimited, ServerError):
            exc = cls("msg", status_code=400)
            assert isinstance(exc, APIError)
            assert isinstance(exc, EFGError)

    def test_order_error_hierarchy(self) -> None:
        for cls in (OrderError, OrderRejected, InsufficientFunds, InvalidOrder):
            exc = cls("msg")
            assert isinstance(exc, EFGError)
            assert isinstance(exc, OrderError)

    def test_invalid_symbol(self) -> None:
        exc = InvalidSymbol("FAKE", market_id=1)
        assert isinstance(exc, EFGError)
        assert exc.symbol == "FAKE"
        assert exc.market_id == 1
        assert "FAKE" in str(exc)

    def test_config_error(self) -> None:
        exc = ConfigError("missing EFG_PARTNER_ID")
        assert isinstance(exc, EFGError)


class TestEnums:
    """Verify documented enum values are correct."""

    def test_operation_types(self) -> None:
        assert OperationType.BUY == 100
        assert OperationType.SELL == 200

    def test_order_expire_terms(self) -> None:
        assert OrderExpireTerm.DAY == 7
        assert OrderExpireTerm.GOOD_TILL_DATE == 8

    def test_order_via_api(self) -> None:
        assert OrderVia.API == 8

    def test_order_category_normal(self) -> None:
        assert OrderCategory.NORMAL == 0

    def test_execution_instruction_default(self) -> None:
        assert ExecutionInstruction.DEFAULT == 1


class TestSettings:
    """Test Settings configuration loading."""

    def test_settings_from_kwargs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        for var in ("EFG_SIMULATION", "EFG_IDENTITY_URL"):
            monkeypatch.delenv(var, raising=False)
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
        )
        assert s.partner_id == "pid"
        assert s.partner_secret == "psec"
        assert s.trading_uuid == "uuid"
        assert s.simulation is False
        assert s.company_code == "003"
        assert s.accept_language == "en"

    def test_default_values(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        for var in ("EFG_SIMULATION", "EFG_IDENTITY_URL"):
            monkeypatch.delenv(var, raising=False)
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
        )
        assert s.timeout_seconds == 30.0
        assert s.default_market_id == 1
        assert "trading.read" in s.scopes
        assert "trading.write" in s.scopes

    def test_base_url_is_a_constant_not_a_settings_field(self) -> None:
        """base_url must not be configurable via Settings/env — it's a fixed module constant."""
        assert "base_url" not in Settings.model_fields
        assert config._BASE_URL == "https://tradingapis.efghermesone.com"

    def test_identity_url_defaults_to_base_url_constant(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        for var in ("EFG_SIMULATION", "EFG_IDENTITY_URL"):
            monkeypatch.delenv(var, raising=False)
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
        )
        assert s.identity_url == config._BASE_URL

    def test_streaming_url_is_a_constant_not_a_settings_field(self) -> None:
        """Streaming URL must not be configurable via Settings/env — no sim/prod split."""
        assert "streaming_url" not in Settings.model_fields
        assert "streaming_url_prod" not in Settings.model_fields
        assert "streaming_url_sim" not in Settings.model_fields
        assert config._STREAMING_URL == "https://iengine138.hermesonline.com/"

    def test_simulation_docstring_notes_no_streaming_effect(self) -> None:
        description = Settings.model_fields["simulation"].description
        assert description is not None
        assert "streaming" in description.lower()
        assert "production host" in description.lower()

    def test_simulation_mode(self) -> None:
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
            simulation=True,
        )
        assert s.server_select_header == "simulation"

    def test_real_mode(self) -> None:
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
            simulation=False,
        )
        assert s.server_select_header == "real"

    def test_invalid_language_raises(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                partner_id="pid",
                partner_secret="psec",
                trading_uuid="uuid",
                accept_language="fr",
            )

    def test_scope_string(self) -> None:
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
            scopes=["trading.read"],
        )
        assert s.scope_string == "trading.read"

    def test_scopes_from_space_separated_string(self) -> None:
        s = Settings(
            partner_id="pid",
            partner_secret="psec",
            trading_uuid="uuid",
            scopes="trading.read trading.write",  # type: ignore[arg-type]
        )
        assert "trading.read" in s.scopes
        assert "trading.write" in s.scopes

    def test_env_var_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_PARTNER_ID", "env-pid")
        monkeypatch.setenv("EFG_PARTNER_SECRET", "env-sec")
        monkeypatch.setenv("EFG_TRADING_UUID", "env-uuid")
        monkeypatch.setenv("EFG_SIMULATION", "true")
        s = Settings()
        assert s.partner_id == "env-pid"
        assert s.simulation is True

    def test_constructor_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EFG_PARTNER_ID", "env-pid")
        monkeypatch.setenv("EFG_PARTNER_SECRET", "env-sec")
        monkeypatch.setenv("EFG_TRADING_UUID", "env-uuid")
        s = Settings(partner_id="override-pid")
        assert s.partner_id == "override-pid"
