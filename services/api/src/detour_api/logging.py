"""Structured JSON logging with redaction.

Rules:
* Values under sensitive keys (token, secret, password, authorization, cookie, api key, database
  url) are replaced before anything is written.
* Bearer tokens and ``user:password@`` parts of URLs are scrubbed from free text as well, so a
  secret in an exception message does not reach the log.
* Request logs carry the method, the path (never the query string), the status and the duration.
  Headers and bodies are never logged.
"""

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "api-key",
    "database_url",
    "credential",
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_DT_TOKEN = re.compile(r"\bdt1\.[0-9a-f]{32}\.[A-Za-z0-9_-]{43}\b")


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def scrub_text(text: str) -> str:
    text = _BEARER.sub(rf"\1 {REDACTED}", text)
    text = _URL_CREDENTIALS.sub(rf"\1{REDACTED}@", text)
    return _DT_TOKEN.sub(REDACTED, text)


def redact(value: Any, key: str | None = None) -> Any:
    """Return a copy of ``value`` with secrets removed."""
    if key is not None and _is_sensitive(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def redaction_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    return {str(k): redact(v, str(k)) for k, v in event_dict.items()}


def configure_logging(level: str = "INFO") -> None:
    """Send structlog and the standard library (uvicorn, alembic, sqlalchemy) to JSON on stdout."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,  # before redaction, so tracebacks are scrubbed
        redaction_processor,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(sort_keys=True),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # HTTP client libraries log full URLs, query strings included, at INFO.
    # httpx2 and httpcore2 are what Starlette's TestClient prefers when installed (they are not
    # a dependency of this project, but a machine may have them); silence them as well.
    for name in ("httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        named = logging.getLogger(name)
        named.handlers = []
        named.propagate = True


def get_logger(name: str = "detour") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
