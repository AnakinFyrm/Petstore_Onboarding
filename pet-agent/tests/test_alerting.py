"""Tests for the alerting seam."""

import logging

import pytest

from pet_agent.alerting import Alerter, LogAlerter, NullAlerter, Severity


def test_log_alerter_emits_at_error_by_default(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        LogAlerter().alert("downstream rejected every payload")
    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert "downstream rejected every payload" in record.getMessage()


@pytest.mark.parametrize(
    ("severity", "expected_level"),
    [
        (Severity.WARNING, logging.WARNING),
        (Severity.ERROR, logging.ERROR),
        (Severity.CRITICAL, logging.CRITICAL),
    ],
)
def test_log_alerter_maps_severity_to_level(
    severity: Severity, expected_level: int, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        LogAlerter().alert("something", severity=severity)
    assert caplog.records[-1].levelno == expected_level


def test_log_alerter_attaches_context(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        LogAlerter().alert("job stuck", job_id=42)
    record = caplog.records[-1]
    assert getattr(record, "job_id", None) == 42
    assert getattr(record, "alert", None) is True


def test_null_alerter_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        NullAlerter().alert("ignored", severity=Severity.CRITICAL)
    assert not caplog.records


def test_both_implementations_satisfy_the_protocol() -> None:
    alerters: list[Alerter] = [LogAlerter(), NullAlerter()]
    for alerter in alerters:
        alerter.alert("smoke")
