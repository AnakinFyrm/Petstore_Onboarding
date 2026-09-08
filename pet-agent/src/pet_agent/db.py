"""Postgres access: a connection pool and the schema applier.

There is no ORM and no migration framework here, by convention: the SQL stays
visible, and ``init.sql`` is written to be idempotent so applying it on every
start is safe. The cost of that choice is that schema changes must be additive
(``CREATE TABLE IF NOT EXISTS``, ``ADD COLUMN IF NOT EXISTS``) and code has to
tolerate rows written by an older version.

``asyncpg`` ships no type stubs, so the pool is typed as ``Any`` rather than
scattering ignores through every caller.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

import asyncpg

LOGGER = logging.getLogger(__name__)


async def create_pool(
    dsn: str,
    *,
    min_size: int = 1,
    max_size: int = 5,
    attempts: int = 1,
    backoff_seconds: float = 1.0,
) -> Any:
    """Open a connection pool, retrying while the database refuses connections.

    A container frequently starts before Postgres is accepting connections, so the
    first attempt failing is normal rather than fatal. Backoff grows linearly and
    the last failure is raised so a genuinely misconfigured DSN still stops the
    process instead of retrying forever.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
        except (OSError, asyncpg.PostgresError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            delay = backoff_seconds * attempt
            LOGGER.warning(
                "Database not reachable (attempt %d/%d): %s; retrying in %.1fs",
                attempt,
                attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Could not connect to the database after {attempts} attempt(s)") from last_error


async def check_connection(pool: Any) -> bool:
    """Return True when the pool can serve a trivial query.

    Used by the readiness probe: a pool object exists long after the database
    behind it has gone away, so readiness has to actually ask.
    """
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        LOGGER.warning("Database readiness check failed", exc_info=True)
        return False
    return True


async def apply_schema(pool: Any, schema_path: Path) -> None:
    """Apply the DDL in ``schema_path``. Safe to call on every start."""
    # Read off the event loop: this runs during startup, and blocking the loop on
    # file IO would stall everything else the lifespan handler is doing.
    sql = await asyncio.to_thread(Path(schema_path).read_text, encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)
    LOGGER.info("Applied schema from %s", schema_path)
