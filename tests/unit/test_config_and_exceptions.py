"""Unit tests for config, exceptions, and enums."""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from younit import config
from younit.client import Client
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

SIMULATION_DISABLED_MESSAGE = (
    "EFG_SIMULATION is temporarily disabled in this version while simulation mode "
    "is being verified. Remove EFG_SIMULATION to continue."
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
        exc = ConfigError("missing TRADING_ID")
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

    @pytest.fixture(autouse=True)
    def isolate_environment(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        for variable in ("TRADING_ID", "API_KEY", "EFG_SIMULATION"):
            monkeypatch.delenv(variable, raising=False)

    def test_settings_from_kwargs(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        s = Settings(
            trading_id="test-id",
            api_key="test-key",
        )
        assert s.trading_id == "test-id"
        assert s.api_key.get_secret_value() == "test-key"
        assert s.simulation is False
        assert s.company_code == "003"
        assert s.accept_language == "en"

    def test_default_values(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        s = Settings(
            trading_id="test-id",
            api_key="test-key",
        )
        assert s.timeout_seconds == 30.0
        assert s.default_market_id == 1

    def test_base_url_is_a_constant_not_a_settings_field(self) -> None:
        """base_url must not be configurable via Settings/env â€” it's a fixed module constant."""
        assert "base_url" not in Settings.model_fields
        assert config._BASE_URL == "https://tradingapis.efghermesone.com"

    def test_token_url_uses_production_host(self) -> None:
        assert config._TOKEN_URL == ("https://tradingapis.efghermesone.com/api/public-keys/token")

    def test_streaming_url_is_a_constant_not_a_settings_field(self) -> None:
        """Streaming URL must not be configurable via Settings/env â€” no sim/prod split."""
        assert "streaming_url" not in Settings.model_fields
        assert "streaming_url_prod" not in Settings.model_fields
        assert "streaming_url_sim" not in Settings.model_fields
        assert config._STREAMING_URL == "https://iengine138.hermesonline.com/"

    def test_simulation_defaults_to_false(self) -> None:
        s = Settings(trading_id="test-id", api_key="test-key")
        assert s.simulation is False
        assert s.server_select_header == "real"

    @pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
    def test_true_simulation_env_raises_config_error(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ) -> None:
        monkeypatch.setenv("TRADING_ID", "env-id")
        monkeypatch.setenv("API_KEY", "env-key")
        monkeypatch.setenv("EFG_SIMULATION", value)
        with pytest.raises(ConfigError) as exc_info:
            Settings()
        assert exc_info.value.message == SIMULATION_DISABLED_MESSAGE

    def test_true_simulation_kwarg_raises_config_error(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            Settings(trading_id="test-id", api_key="test-key", simulation=True)
        assert exc_info.value.message == SIMULATION_DISABLED_MESSAGE

    def test_false_simulation_env_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADING_ID", "env-id")
        monkeypatch.setenv("API_KEY", "env-key")
        monkeypatch.setenv("EFG_SIMULATION", "false")
        assert Settings().simulation is False

    def test_client_fails_at_startup_when_simulation_env_is_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TRADING_ID", "env-id")
        monkeypatch.setenv("API_KEY", "env-key")
        monkeypatch.setenv("EFG_SIMULATION", "true")
        with pytest.raises(ConfigError, match="EFG_SIMULATION is temporarily disabled"):
            Client(lazy_auth=True, lazy_symbols=True)

    def test_client_fails_at_startup_when_simulation_arg_is_true(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            Client(trading_id="test-id", api_key="test-key", simulation=True, lazy_auth=True)
        assert exc_info.value.message == SIMULATION_DISABLED_MESSAGE

    def test_real_mode(self) -> None:
        s = Settings(
            trading_id="test-id",
            api_key="test-key",
            simulation=False,
        )
        assert s.server_select_header == "real"

    def test_env_examples_do_not_mention_simulation(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[2]
        env_example = root / ".env.example"
        assert env_example.read_text(encoding="utf-8").splitlines()[0] == (
            "TRADING_ID=your-trading-id"
        )
        for path in (env_example, root / "examples" / "mcp" / "ai_client" / ".env.example"):
            assert "EFG_SIMULATION" not in path.read_text(encoding="utf-8"), path

    def test_mcp_tool_descriptions_do_not_mention_paper_trading(self) -> None:
        import asyncio

        from younit.mcp_server import server as mcp_server
        from younit.mcp_server.safety import SafetySettings

        settings = SafetySettings()
        settings.readonly = False
        mcp_server.configure_write_tools(settings)
        try:
            tools = asyncio.run(mcp_server.app.list_tools())
        finally:
            mcp_server._remove_write_tools()
        assert {"buy", "sell", "buy_fund", "sell_fund"} <= {t.name for t in tools}
        for tool in tools:
            text = (tool.description or "").lower()
            assert "paper" not in text, tool.name
            assert "simulation" not in text, tool.name

    def test_invalid_language_raises(self) -> None:
        with pytest.raises(ValidationError):
            Settings(
                trading_id="test-id",
                api_key="test-key",
                accept_language="fr",
            )

    def test_env_var_loading(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADING_ID", "env-id")
        monkeypatch.setenv("API_KEY", "env-key")
        s = Settings()
        assert s.trading_id == "env-id"
        assert s.api_key.get_secret_value() == "env-key"
        assert s.simulation is False

    def test_constructor_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRADING_ID", "env-id")
        monkeypatch.setenv("API_KEY", "env-key")
        s = Settings(trading_id="override-id", api_key="override-key")
        assert s.trading_id == "override-id"
        assert s.api_key.get_secret_value() == "override-key"

    def test_dotenv_loading_and_constructor_precedence(self, tmp_path):
        (tmp_path / ".env").write_text("TRADING_ID=file-id\nAPI_KEY=file-key\n")
        settings = Settings()
        assert settings.trading_id == "file-id"
        assert settings.api_key.get_secret_value() == "file-key"
        overridden = Settings(trading_id="override-id", api_key="override-key")
        assert overridden.trading_id == "override-id"
        assert overridden.api_key.get_secret_value() == "override-key"

    @pytest.mark.parametrize("missing", ["TRADING_ID", "API_KEY"])
    def test_missing_credentials_named_in_error(self, monkeypatch, missing):
        provided = "API_KEY" if missing == "TRADING_ID" else "TRADING_ID"
        monkeypatch.setenv(provided, "test-value")
        with pytest.raises(ConfigError, match=missing) as caught:
            Client(lazy_auth=True, lazy_symbols=True)
        assert "test-value" not in str(caught.value)

    def test_missing_both_credentials(self):
        with pytest.raises(ConfigError) as caught:
            Client(lazy_auth=True, lazy_symbols=True)
        assert "TRADING_ID" in str(caught.value)
        assert "API_KEY" in str(caught.value)

    @pytest.mark.parametrize("field", ["trading_id", "api_key"])
    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_credentials_are_rejected(self, field, value):
        kwargs = {"trading_id": "test-id", "api_key": "test-key", field: value}
        with pytest.raises(ConfigError, match=field):
            Client(**kwargs, lazy_auth=True, lazy_symbols=True)

    def test_settings_repr_does_not_include_credentials(self):
        settings = Settings(trading_id="test-id", api_key="test-key")
        assert "test-id" not in repr(settings)
        assert "test-key" not in repr(settings)
