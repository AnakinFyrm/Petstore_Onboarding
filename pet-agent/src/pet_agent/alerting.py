"""A seam for telling a human that something needs attention.

This is deliberately separate from logging and telemetry. Those answer "what
happened" for someone already looking; an alert is for something nobody is
looking at yet and which will not fix itself -- a payload that cannot be
processed after every retry, a downstream service rejecting everything, a
business rule that has been violated.

:class:`LogAlerter` is the default so nothing has to be configured to start with,
and it keeps alerts visible in the logs. Swap in a Teams, Slack or PagerDuty
implementation later without touching call sites: they only depend on the
:class:`Alerter` protocol.

Keep alerts rare and actionable. An alert that fires routinely trains people to
ignore it, at which point it is worse than no alert.
"""

import logging
from enum import StrEnum
from typing import Any, Protocol

LOGGER = logging.getLogger(__name__)


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Alerter(Protocol):
    """Sends a notification a human is expected to act on."""

    def alert(self, message: str, *, severity: Severity = Severity.ERROR, **context: Any) -> None: ...


class LogAlerter:
    """Writes the alert to the log. The default, and a fine choice when logs are shipped."""

    def alert(self, message: str, *, severity: Severity = Severity.ERROR, **context: Any) -> None:
        level = logging.CRITICAL if severity is Severity.CRITICAL else logging.ERROR
        if severity is Severity.WARNING:
            level = logging.WARNING
        LOGGER.log(level, "ALERT %s: %s", severity.value, message, extra={"alert": True, **context})


class NullAlerter:
    """Discards alerts. For tests that assert on behaviour rather than noise."""

    def alert(self, message: str, *, severity: Severity = Severity.ERROR, **_context: Any) -> None:  # noqa: ARG002 - the signature is fixed by the Alerter protocol
        return
