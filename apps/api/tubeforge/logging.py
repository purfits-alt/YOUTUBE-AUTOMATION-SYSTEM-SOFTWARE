"""Structured JSON logging with secret redaction (OAUTH_SECURITY §5).

Every log event passes through :func:`redact_event` before rendering, so tokens, keys,
passwords and DSN passwords never reach the log files, even when logged by mistake.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "***"

SENSITIVE_KEY = re.compile(
    r"(token|secret|password|passwd|passphrase|authorization|cookie|api[_-]?key|"
    r"code[_-]?verifier|session[_-]?uri|private[_-]?key|credential)",
    re.IGNORECASE,
)

# (pattern, replacement) applied to every string value.
SENSITIVE_VALUES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer " + REDACTED),
    (re.compile(r"\bya29\.[A-Za-z0-9._-]+"), REDACTED),  # Google OAuth access token
    (re.compile(r"\b1//[A-Za-z0-9._-]{20,}"), REDACTED),  # Google OAuth refresh token
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), REDACTED),  # Google API key
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"), REDACTED),  # Groq API key
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"), REDACTED),  # Telegram bot token
    (re.compile(r"(postgres(?:ql)?(?:\+\w+)?://[^:/@\s]+:)[^@\s]+@"), r"\1" + REDACTED + "@"),
)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        for pattern, replacement in SENSITIVE_VALUES:
            value = pattern.sub(replacement, value)
        return value
    if isinstance(value, Mapping):
        return {k: (REDACTED if _is_sensitive_key(k) else redact_value(v)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return type(value)(redact_value(v) for v in value)
    return value


def _is_sensitive_key(key: object) -> bool:
    return isinstance(key, str) and bool(SENSITIVE_KEY.search(key))


def redact_event(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict.keys()):
        event_dict[key] = REDACTED if _is_sensitive_key(key) else redact_value(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            redact_event,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
