"""Configuration for the EFG API SDK.

All settings can be provided via constructor arguments or environment variables.
Environment variables are prefixed with ``EFG_``.

Example::

    # From environment (e.g. in a .env file or shell):
    # EFG_PARTNER_ID=your-partner-id
    # EFG_PARTNER_SECRET=your-partner-secret
    # EFG_TRADING_UUID=client-trading-uuid
    # EFG_SIMULATION=true

    from younit.config import Settings

    settings = Settings()  # reads from env

    # Or override explicitly:
    settings = Settings(
        partner_id="...",
        partner_secret="...",
        trading_uuid="...",
        simulation=True,
    )
"""

from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Confirmed production hosts. Hardcoded intentionally — no longer configurable
# via env var or public constructor argument. For internal/staging use only,
# Client accepts an undocumented `_base_url_override` constructor kwarg.
_BASE_URL = "https://tradingapis.efghermesone.com"
_STREAMING_URL = "https://iengine138.hermesonline.com/"


class Settings(BaseSettings):
    """EFG API client configuration.

    All fields can be set via environment variables (prefixed ``EFG_``).
    Constructor arguments take precedence over environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="EFG_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required credentials ---

    partner_id: str = Field(
        ...,
        description="Partner identifier issued by the trading provider. Set EFG_PARTNER_ID.",
    )
    partner_secret: str = Field(
        ...,
        description="Partner secret issued by the trading provider. Set EFG_PARTNER_SECRET.",
    )
    trading_uuid: str = Field(
        ...,
        description=(
            "Trading UUID for the end client. Each client has a unique UUID "
            "assigned by the trading provider. Set EFG_TRADING_UUID."
        ),
    )

    # --- Endpoints ---

    identity_url: str | None = Field(
        default=None,
        description=(
            "Base URL for the identity provider. "
            "Defaults to the production trading API host when not set. Set EFG_IDENTITY_URL."
        ),
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
    scopes: list[str] = Field(
        default=["trading.read", "trading.write"],
        description=(
            "OAuth scopes to request. Space-separated string or JSON list. "
            "Set EFG_SCOPES='trading.read trading.write'."
        ),
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
            "Default market identifier. 1 = EGX (Egypt Stock Exchange). Set EFG_DEFAULT_MARKET_ID."
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
            "Lightstreamer adapter for the ActiveOrders stream. Set EFG_STREAMING_ADAPTER_TRADING."
        ),
    )

    @model_validator(mode="after")
    def _apply_defaults(self) -> Settings:
        """Default identity_url to the production trading API host when unset."""
        if not self.identity_url:
            self.identity_url = _BASE_URL
        return self

    @field_validator("accept_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate that the language is one of the supported values."""
        if v not in ("en", "ar"):
            raise ValueError(f"accept_language must be 'en' or 'ar', got {v!r}")
        return v

    @field_validator("scopes", mode="before")
    @classmethod
    def parse_scopes(cls, v: str | list[str]) -> list[str]:
        """Allow scopes to be provided as a space-separated string."""
        if isinstance(v, str):
            return v.split()
        return v

    @property
    def server_select_header(self) -> str:
        """Return the X-Server-Select header value based on simulation mode."""
        return "simulation" if self.simulation else "real"

    @property
    def scope_string(self) -> str:
        """Return scopes as a space-separated string for OAuth requests."""
        return " ".join(self.scopes)
