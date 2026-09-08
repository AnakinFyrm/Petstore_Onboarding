"""Telemetry: Pydantic Logfire traces, metrics and log correlation.

Token-gated and fail-open. With no ``LOGFIRE_TOKEN`` set, Logfire is never
configured, nothing leaves the process, and the service behaves exactly as it
would without this module. ``TELEMETRY_ENABLED=false`` forces it off even when a
token is present. A failure inside setup is logged and swallowed: telemetry must
never be the reason a service will not start.

Logfire is imported lazily inside :func:`setup_telemetry` so the package still
imports, and the test suite still runs, when the dependency is unused.

Log records are bridged into Logfire so ordinary ``LOGGER.info`` calls are
searchable next to spans. The local stdout handler is kept as well, because
container logs are what you read during an incident when the telemetry backend
is the thing that is broken.
"""

import logging
from importlib.metadata import PackageNotFoundError, version

from pet_agent.config import Settings

LOGGER = logging.getLogger(__name__)

# Values that must never reach a telemetry backend even if they appear in a span
# attribute or a log field. Logfire's own defaults already cover passwords and
# tokens; these are the names this project uses.
SCRUB_PATTERNS = ["dsn", "signing", "api[-_]?key", "secret"]


def _service_version() -> str:
    try:
        return version("pet-agent")
    except PackageNotFoundError:
        return "unknown"


def setup_telemetry(settings: Settings) -> bool:
    """Configure Logfire. Returns True when telemetry is active.

    Call once per process, from the entry point, before serving traffic.
    """
    if not settings.telemetry_enabled:
        LOGGER.debug("Telemetry disabled by TELEMETRY_ENABLED")
        return False
    if settings.logfire_token is None:
        LOGGER.debug("LOGFIRE_TOKEN is not set; running without telemetry")
        return False

    import logfire

    try:
        logfire.configure(
            token=settings.logfire_token.get_secret_value(),
            send_to_logfire=True,
            service_name=settings.service_name,
            service_version=_service_version(),
            environment=settings.app_env,
            # The project's own handler owns stdout; Logfire's console output
            # would duplicate every line.
            console=False,
            scrubbing=logfire.ScrubbingOptions(extra_patterns=SCRUB_PATTERNS),
        )
        logging.getLogger().addHandler(logfire.LogfireLoggingHandler())
        logfire.instrument_httpx()
        logfire.instrument_asyncpg()
        # Agent runs, tool calls and token usage become spans.
        logfire.instrument_pydantic_ai()
    except Exception:
        LOGGER.exception("Telemetry setup failed; continuing without it")
        return False

    LOGGER.info("Telemetry active (service=%s environment=%s)", settings.service_name, settings.app_env)
    return True
