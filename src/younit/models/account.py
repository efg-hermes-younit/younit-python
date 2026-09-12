"""Pydantic models for account and profile data."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Profile(BaseModel):
    """A trading profile / sub-account belonging to a client.

    Attributes:
        profile_id: Numeric identifier for this trading profile.
            Used in order placement and buying-power requests.
        profile_name: Human-readable name for this profile.
    """

    model_config = ConfigDict(populate_by_name=True)

    profile_id: int = Field(alias="profileId")
    profile_name: str | None = Field(default=None, alias="profileName")


class AccountInfo(BaseModel):
    """Client account information returned by GET /api/account-utils/GetAccountInfo.

    Attributes:
        account_code: Internal numeric account identifier.
        client_name: Client's full name (Arabic).
        name: Client's full name (same as client_name).
        email: Client's email address.
        mobile: Client's mobile phone number.
        investor_code: Investor code assigned by the exchange.
        can_setup_datafeed: Whether the client can configure a live datafeed.
        is_live_datafeed: Whether the client has an active live datafeed.
        is_global_market_allowed: Whether global market trading is enabled.
        can_edit_mobile: Whether the mobile number can be edited.
        can_edit_email: Whether the email address can be edited.
    """

    model_config = ConfigDict(populate_by_name=True)

    account_code: int | None = Field(default=None, alias="accountCode")
    client_name: str | None = Field(default=None, alias="clientName")
    name: str | None = Field(default=None, alias="name")
    email: str | None = Field(default=None, alias="email")
    mobile: str | None = Field(default=None, alias="mobile")
    investor_code: str | None = Field(default=None, alias="investorCode")
    can_setup_datafeed: bool = Field(default=False, alias="canSetupDatafeed")
    is_live_datafeed: bool = Field(default=False, alias="isLiveDatafeed")
    is_global_market_allowed: bool | None = Field(default=None, alias="isGlobalMarketAllowed")
    can_edit_mobile: bool = Field(default=False, alias="canEditMobile")
    can_edit_email: bool = Field(default=False, alias="canEditEmail")
