"""Structured logging setup for the EFG API SDK.

Uses ``structlog`` for structured, context-rich log output.

Sensitive data policy:
- Tokens, credentials, and passwords are NEVER logged at any level.
- Full request/response bodies are NOT logged by default.
- Enable ``EFG_DEBUG=true`` for verbose logging (headers and summaries only;
  credential values are still redacted).
"""

from __future__ import annotations

import logging
import sys

import structlog

# Keys whose values must always be redacted in log output
_REDACTED_KEYS = frozenset(
    {
        "access_token",
        "client_token",
        "server_token",
        "token",
        "partner_secret",
        "password",
        "Authorization",
        "authorization",
    }
)

_REDACTED_PLACEHOLDER = "***REDACTED***"


def _redact_sensitive(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Processor that redacts sensitive fields from all log events."""
    for key in _REDACTED_KEYS:
        if key in event_dict:
            event_dict[key] = _REDACTED_PLACEHOLDER
    return event_dict


def configure_logging(level: str = "INFO", *, debug: bool = False) -> None:
    """Configure structlog for the SDK.

    Args:
        level: Standard log level string (e.g. ``"INFO"``, ``"DEBUG"``).
        debug: If True, enables verbose output. Sensitive values are still
            redacted even in debug mode.
    """
    log_level = logging.DEBUG if debug else getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    shared_processors: list[structlog.types.Processor] = [
        _redact_sensitive,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A bound structlog logger with redaction pre-configured.
    """
    return structlog.get_logger(name)  # type: ignore[return-value]
