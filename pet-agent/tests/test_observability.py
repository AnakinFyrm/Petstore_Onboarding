"""Tests for telemetry setup.

The behaviour that matters is that telemetry is optional: an unconfigured or
broken backend must never stop the service. No test here contacts Logfire.
"""

import pytest
from pydantic import SecretStr

from pet_agent.config import Settings
from pet_agent.observability import SCRUB_PATTERNS, setup_telemetry


def test_no_token_means_telemetry_is_off() -> None:
    assert setup_telemetry(Settings()) is False


def test_explicitly_disabled_even_with_a_token() -> None:
    settings = Settings(telemetry_enabled=False, logfire_token=SecretStr("dummy-token"))
    assert setup_telemetry(settings) is False


def test_setup_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # A broken backend, a bad token, an incompatible version: none of it may stop
    # the process from starting.
    import logfire

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("logfire is unhappy")

    monkeypatch.setattr(logfire, "configure", explode)
    settings = Settings(logfire_token=SecretStr("dummy-token"))
    assert setup_telemetry(settings) is False


def test_scrub_patterns_cover_this_project_s_secret_names() -> None:
    joined = " ".join(SCRUB_PATTERNS)
    assert "dsn" in joined
    assert "secret" in joined
