"""Tests for the logging wiring.

The implementation is fyrm-service-core's and is pinned by that library's own
suite; here we prove the re-export path works and that the two behaviours this
service relies on — the correlation id and redaction-on-by-default — are
active through it.
"""

import logging
from collections.abc import Iterator

import pytest

from pet_agent.logging_config import (
    JsonFormatter,
    RedactionFilter,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    set_correlation_id(None)


def make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("test.logger", logging.INFO, __file__, 1, message, None, None)


def test_setup_logging_wires_the_library() -> None:
    setup_logging(level="INFO", log_format="json")
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)
    assert any(isinstance(f, RedactionFilter) for f in handler.filters), "redaction must be on by default"


def test_correlation_id_roundtrips() -> None:
    set_correlation_id("abc-123")
    assert get_correlation_id() == "abc-123"


def test_redaction_replaces_secret_shaped_fields() -> None:
    record = make_record()
    record.api_key = "s3cret-value"
    assert RedactionFilter().filter(record) is True
    # Read through __dict__: LogRecord's extra fields are dynamic attributes.
    assert record.__dict__["api_key"] == "[redacted]"
