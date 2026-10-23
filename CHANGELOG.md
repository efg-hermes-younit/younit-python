# Changelog

All notable changes to `younit` will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed - Breaking
- Authentication now uses TRADING_ID and API_KEY via the public-keys token endpoint; EFG_PARTNER_ID, EFG_PARTNER_SECRET and EFG_TRADING_UUID are removed.
- Removed obsolete identity-host and OAuth-scope configuration. REST hosts
  are unchanged; Lightstreamer uses the trading ID and the refreshed token.
- The token response parser uses the production `accessToken`, `expiresIn`,
  and `tokenType` fields, accepting them inside `data` or at the top level.

### Added
- Initial implementation of the EFG ONE Python SDK
- `Client` class with full trading API coverage
- Automatic token lifecycle management with proactive and 401-triggered refresh
- MCP server with configurable safety controls
- Structured logging with mandatory credential redaction
- GitHub Actions CI/CD workflows
- `top_movers` MCP tool wrapping `Client.get_top_movers()` — returns the full
  tradeable-stock universe sorted by `change_pct` (gainers first, losers
  last), computed live over the streaming feed the same way the official
  EFG app does it.
- 9 new MCP tools, closing a gap where several `Client` methods already
  demonstrated in `examples/` had no MCP tool equivalent: `market_status`,
  `positions_split`, `fund_positions`, `list_by_class`,
  `list_same_day_eligible`, `list_otc` (read tools), and `buy_fund`,
  `sell_fund`, `cancel_fund_order` (write tools, same safety controls as
  `buy`/`sell`). MCP server now registers 30 tools total (23 read + 7 write).

### Fixed
- MCP `sell` tool was missing the `settlement` parameter entirely, silently
  hardcoding the SDK's `"t2"` default — same-day (T0) sells (incl. limit
  orders, fixed earlier in `Client.sell()`/`place_order()`) were unreachable
  via MCP even though the underlying SDK already supported them. The tool
  now accepts `settlement="t0"|"t1"|"t2"` and passes it through to
  `Client.sell()`. `list_stocks`/`trending_stocks`/`search_stocks` MCP tool
  docstrings also updated to document `security_class_name` and
  `is_same_day_eligible` — these fields were already present in the
  returned data (full `StockInfo.model_dump()`) but undocumented, so an AI
  agent reading only the tool description wouldn't know to check them
  before attempting a same-day order.
- `top_gainers` / `top_losers` MCP tools. The backend team confirmed the
  underlying REST endpoint (`get_top_gainers_losers`) is not a dedicated
  server-side computation and may return incomplete/stale data — replaced
  by the `top_movers` MCP tool above so an AI agent can no longer pick the
  unreliable option. The SDK methods `Client.top_gainers()`/
  `Client.top_losers()` are unaffected and remain available for direct SDK use.
- Removed the single-leaf-cert TLS pinning workaround (`VERIFY_X509_PARTIAL_CHAIN`
  + `certs/efghermesone-identity.pem`) that was in place from ~2026-08 to
  2026-09-13 to route around what appeared to be a broken certificate chain
  on `tradingapis.efghermesone.com`. Live verification on 2026-09-13 confirmed
  the server now sends a complete, valid chain (leaf → Thawte intermediate →
  DigiCert root) and that a full real auth + API call flow succeeds
  end-to-end under standard system-trust TLS verification, so the pin (and
  its `SECLEVEL=1` cipher downgrade) was removed. The retired cert is kept
  at `diagnostics/efghermesone-identity-pinned-cert.pem` as a rollback
  safety net.

---

## [0.1.0] — (planned)

Initial public release.

[Unreleased]: https://github.com/efg-hermes-younit/younit-python-sdk/compare/v0.1.0...HEAD
