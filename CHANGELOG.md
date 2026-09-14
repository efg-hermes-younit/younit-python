# Changelog

All notable changes to `younit` will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Initial implementation of the EFG ONE Python SDK
- `Client` class with full trading API coverage
- Automatic token lifecycle management (server → client token)
- MCP server with configurable safety controls
- Structured logging with mandatory credential redaction
- GitHub Actions CI/CD workflows

### Removed
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

[Unreleased]: https://github.com/efg-hermes-younit/younit-python/compare/v0.1.0...HEAD
