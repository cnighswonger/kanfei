"""Shared logging configuration for every Kanfei entrypoint.

Both the web service (`app.main`) and the logger daemon (`logger_main`)
must configure logging identically.  They did not: `main.py` suppressed
httpx's INFO-level request logging, `logger_main.py` did not, and the
logger daemon consequently wrote Weather Underground credentials to the
systemd journal on every upload (#206).

Anything that configures logging should call `configure_logging()` rather
than calling `logging.basicConfig()` directly, so a future entrypoint
cannot reintroduce the same gap.
"""

import logging
import re
from typing import Iterable

LOG_FMT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Loggers that emit request URLs (and therefore any credential carried in a
# query string or path) at INFO.  Held at WARNING so routine traffic is not
# logged at all.
_URL_LOGGING_LIBRARIES = ("httpx", "httpcore")

# Quietened for noise, not secrecy.
_NOISY_LIBRARIES = ("websockets",)

# Query-string parameters whose values must never reach a log.  Matched
# case-insensitively; covers the Weather Underground `PASSWORD` param, API
# keys, and bearer-ish tokens.
_SECRET_PARAMS = (
    "password", "passwd", "pass",
    "key", "apikey", "api_key",
    "token", "access_token", "auth",
    "secret", "passcode",
)

_REDACTED = "***REDACTED***"

# `PASSWORD=hunter2` / `?key=abc&` etc.  Stops at & or whitespace so the
# rest of the URL stays readable.
_QUERY_SECRET_RE = re.compile(
    r"(?i)\b(" + "|".join(map(re.escape, _SECRET_PARAMS)) + r")=([^&\s\"']+)"
)

# Telegram-style secrets embedded in a URL *path* rather than a query
# string: https://api.telegram.org/bot<token>/sendMessage
_PATH_SECRET_RE = re.compile(r"(?i)/bot(\d+:[A-Za-z0-9_-]+)")


def redact(text: str) -> str:
    """Strip credential values out of a string, keeping it readable."""
    text = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}={_REDACTED}", text)
    text = _PATH_SECRET_RE.sub(f"/bot{_REDACTED}", text)
    return text


class RedactSecretsFilter(logging.Filter):
    """Redact credentials from any log record that reaches a handler.

    Defence in depth.  Level suppression alone is fragile: it only helps
    for the specific loggers someone remembered to quieten, and a future
    DEBUG session or a new library re-opens the hole.  This filter applies
    to everything, so a leaked credential has to get past both.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            else:
                record.args = tuple(
                    redact(a) if isinstance(a, str) else a for a in record.args
                )
        return True


def configure_logging(
    level: int = logging.INFO,
    extra_quiet: Iterable[str] = (),
) -> None:
    """Configure root logging for an entrypoint.

    Idempotent enough to call once per process at startup.  Sets the shared
    format, quietens URL-logging libraries, and installs the redaction
    filter on every root handler.
    """
    logging.basicConfig(level=level, format=LOG_FMT, datefmt=LOG_DATEFMT)

    for name in (*_URL_LOGGING_LIBRARIES, *_NOISY_LIBRARIES, *extra_quiet):
        logging.getLogger(name).setLevel(logging.WARNING)

    install_redaction_filter()


def install_redaction_filter() -> None:
    """Attach RedactSecretsFilter to every root handler, once."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RedactSecretsFilter) for f in handler.filters):
            handler.addFilter(RedactSecretsFilter())
