# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✓         |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security issues by emailing:

> **younit-info@efg-hermes.com**

Include:
- A description of the vulnerability
- Steps to reproduce it
- The potential impact
- Any suggested remediation

We aim to acknowledge reports within 2 business days and provide an initial assessment within 5 business days.

## Credential Safety

This SDK is designed with credential safety as a first-class concern:

- Tokens and credentials are **never** logged, even at DEBUG level
- Redacted fields include `access_token`, `client_token`, `token`, `api_key`,
  `API_KEY`, `secret`, `trading_id`, `tradingId`, `TRADING_ID`, `password`,
  and `Authorization`
- No credentials are persisted to disk by default
- The `InMemoryTokenStore` keeps tokens in process memory only
- Custom `TokenStore` implementations must uphold the same guarantee

## Dependency Security

Run `uv audit` (or `pip audit`) regularly to scan for known vulnerabilities in dependencies.
