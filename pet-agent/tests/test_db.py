"""Postgres integration tests.

These need a real database and are skipped unless ``TEST_DATABASE_URL`` is set
(see the ``db_pool`` fixture). Point it at a disposable database: the schema is
applied and rows are written.
"""

from pathlib import Path
from typing import Any

from pet_agent.db import apply_schema


def test_schema_file_exists(schema_path: Path) -> None:
    # Cheap guard that runs without a database: the app applies this file at
    # startup, so a rename must not go unnoticed.
    assert schema_path.is_file()
    assert "CREATE TABLE IF NOT EXISTS" in schema_path.read_text(encoding="utf-8")


async def test_pool_roundtrips(db_pool: Any) -> None:
    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT 1") == 1


async def test_apply_schema_is_idempotent(db_pool: Any, schema_path: Path) -> None:
    # Applied on every start, so running it twice must be a no-op.
    await apply_schema(db_pool, schema_path)
    await apply_schema(db_pool, schema_path)
