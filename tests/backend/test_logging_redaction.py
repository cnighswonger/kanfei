"""Regression tests for credential leakage into logs (#206).

The logger daemon wrote Weather Underground credentials to the systemd
journal on every upload because httpx logs full request URLs at INFO and
only the *web* entrypoint suppressed it.
"""

import logging

import pytest

from app.logging_setup import (
    RedactSecretsFilter,
    configure_logging,
    redact,
)


class TestRedact:
    def test_the_actual_leak(self):
        """The exact URL shape observed in journalctl."""
        url = (
            "GET https://weatherstation.wunderground.com/weatherstation/"
            "updateweatherstation.php?ID=KNCDUNN74&PASSWORD=hunter2"
            "&dateutc=now&tempf=72"
        )
        out = redact(url)
        assert "hunter2" not in out
        # the rest must stay readable for debugging
        assert "ID=KNCDUNN74" in out
        assert "tempf=72" in out

    @pytest.mark.parametrize("param", [
        "PASSWORD", "password", "api_key", "apikey", "token",
        "access_token", "key", "secret", "passcode", "auth",
    ])
    def test_secret_params_redacted_case_insensitively(self, param):
        assert "s3cr3t" not in redact(f"https://x.test/a?{param}=s3cr3t&b=1")

    def test_telegram_token_in_url_path(self):
        """Not a query param — main.py's own comment flagged this shape."""
        out = redact("https://api.telegram.org/bot123456:AAExampleToken/sendMessage")
        assert "AAExampleToken" not in out
        assert "sendMessage" in out

    def test_only_the_value_is_removed(self):
        out = redact("?PASSWORD=abc&station=KNCDUNN74")
        assert "PASSWORD=" in out          # param name kept for context
        assert "abc" not in out
        assert "station=KNCDUNN74" in out

    @pytest.mark.parametrize("benign", [
        "Poll OK: outside_temp=24.8 wind=0.0 baro=1007.5",
        "Archive interval set to 1 minutes",
        "no secrets here, just a=1&b=2",
        "",
    ])
    def test_benign_messages_untouched(self, benign):
        assert redact(benign) == benign


class TestRedactSecretsFilter:
    def _record(self, msg, args=None):
        return logging.LogRecord(
            name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
            msg=msg, args=args, exc_info=None,
        )

    def test_redacts_message(self):
        rec = self._record("GET https://x.test/u?PASSWORD=hunter2 'HTTP/1.1 200 OK'")
        RedactSecretsFilter().filter(rec)
        assert "hunter2" not in rec.getMessage()

    def test_redacts_lazy_format_args(self):
        """httpx formats lazily; the secret can live in args, not msg."""
        rec = self._record("HTTP Request: %s", ("https://x.test/u?PASSWORD=hunter2",))
        RedactSecretsFilter().filter(rec)
        assert "hunter2" not in rec.getMessage()

    def test_filter_always_passes_the_record(self):
        """It redacts; it must never drop a log line."""
        rec = self._record("anything")
        assert RedactSecretsFilter().filter(rec) is True

    def test_non_string_msg_survives(self):
        rec = self._record(12345)
        assert RedactSecretsFilter().filter(rec) is True


class TestConfigureLogging:
    def test_url_logging_libraries_are_quietened(self):
        configure_logging()
        for name in ("httpx", "httpcore"):
            assert logging.getLogger(name).level == logging.WARNING, (
                f"{name} logs full request URLs at INFO — must be >= WARNING"
            )

    def test_redaction_filter_installed_on_root_handlers(self):
        configure_logging()
        root = logging.getLogger()
        assert root.handlers, "expected at least one root handler"
        for h in root.handlers:
            assert any(isinstance(f, RedactSecretsFilter) for f in h.filters)

    def test_idempotent_no_duplicate_filters(self):
        configure_logging()
        configure_logging()
        configure_logging()
        for h in logging.getLogger().handlers:
            n = sum(isinstance(f, RedactSecretsFilter) for f in h.filters)
            assert n <= 1, f"filter installed {n} times"
