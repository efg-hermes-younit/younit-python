"""Configuration for the EFG API SDK.

All settings can be provided via constructor arguments or environment variables.
Credentials use ``TRADING_ID`` and ``API_KEY``. Other settings use ``EFG_``.

Example::

    # From environment (e.g. in a .env file or shell):
    # TRADING_ID=your-trading-id
    # API_KEY=your-api-key
    # EFG_SIMULATION=true

    from younit.config import Settings

    settings = Settings()  # reads from env

    # Or override explicitly:
    settings = Settings(
        trading_id="...",
        api_key="...",
        simulation=True,
    )
"""

from __future__ import annotations

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Confirmed production hosts. Hardcoded intentionally — no longer configurable
# via env var or public constructor argument. For internal/staging use only,
# Client accepts an undocumented `_base_url_override` constructor kwarg.
_BASE_URL = "https://tradingapis.efghermesone.com"
_TOKEN_URL = f"{_BASE_URL}/api/public-keys/token"
_STREAMING_URL = "https://iengine138.hermesonline.com/"


class Settings(BaseSettings):
    """EFG API client configuration.

    Credentials use unprefixed environment variables; other fields use ``EFG_``.
    Constructor arguments take precedence over environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="EFG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    # --- Required credentials ---

    trading_id: str = Field(
        ...,
        validation_alias="TRADING_ID",
        repr=False,
        description="Trading identifier issued by the trading provider. Set TRADING_ID.",
    )
    api_key: SecretStr = Field(
        ...,
        validation_alias="API_KEY",
        repr=False,
        description="Public-key authentication secret. Set API_KEY.",
    )

    # --- Behaviour ---

    simulation: bool = Field(
        default=False,
        description=(
            "When True, sets X-Server-Select: simulation on all requests. "
            "Strongly recommended for initial setup and testing. "
            "Does NOT affect streaming: streaming always connects to the single "
            "production host regardless of this flag. "
            "Set EFG_SIMULATION=true."
        ),
    )
    company_code: str = Field(
        default="003",
        description=(
            "Sets the x-company-code header on all requests. "
            "Valid values: '003', '009'. "
            # DEFERRED: semantics of 003 vs 009 are undocumented; blocked on
            # backend team confirmation.
            "Set EFG_COMPANY_CODE."
        ),
    )
    accept_language: str = Field(
        default="en",
        description="Sets Accept-Language header. 'en' or 'ar'. Set EFG_ACCEPT_LANGUAGE.",
    )
    api_version: str = Field(
        default="1.0",
        description="Sets x-api-version header. Set younit_VERSION.",
    )

    # --- HTTP ---

    timeout_seconds: float = Field(
        default=30.0,
        description="HTTP request timeout in seconds. Set EFG_TIMEOUT_SECONDS.",
        gt=0,
    )

    # --- Logging ---

    log_level: str = Field(
        default="INFO",
        description="Logging level. Set EFG_LOG_LEVEL.",
    )
    debug: bool = Field(
        default=False,
        description=(
            "Enable verbose debug logging. Tokens are still redacted. Set EFG_DEBUG=true."
        ),
    )

    # --- Market defaults ---

    # 1 = EGX (Egypt Stock Exchange), the only market currently supported.
    # market_id parameters exist on SDK methods for future multi-market support.
    default_market_id: int = Field(
        default=1,
        description=(
            "Default market identifier. 1 = EGX (Egypt Stock Exchange). "
            "Set EFG_DEFAULT_MARKET_ID."
        ),
        gt=0,
    )

    # --- Streaming ---

    streaming_adapter: str = Field(
        default="PROXY_MarketBeat",
        description="Lightstreamer adapter for market data streams. Set EFG_STREAMING_ADAPTER.",
    )
    streaming_adapter_trading: str = Field(
        default="PROXY_MarketBeatTrading",
        description=(
            "Lightstreamer adapter for the ActiveOrders stream. "
            "Set EFG_STREAMING_ADAPTER_TRADING."
        ),
    )

    @field_validator("trading_id", "api_key", mode="before")
    @classmethod
    def validate_credentials(cls, value: object) -> object:
        """Reject empty credentials without including their values in errors."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Credential must be a non-empty string.")
        return value

    @field_validator("accept_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that the language is one of the supported values."""
        if v not in ("en", "ar"):
            raise ValueError(f"accept_language must be 'en' or 'ar', got {v!r}")
        return v

    @property
    def server_select_header(self) -> str:
        """Return the X-Server-Select header value based on simulation mode."""
        return "simulation" if self.simulation else "real"
