"""Shared fixtures.

Two rules hold for the whole suite: a test never reads the developer's env files
(``load_env_files`` skips them under pytest unless a test opts in with
``force=True``), and a test never sees another test's settings, because the
``get_settings`` cache and the project's environment variables are reset around
each one.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pet_agent.config import Settings, get_settings

# Every variable the service reads. Cleared between tests so a value set by one
# test, or exported in the developer's shell, cannot influence another.
MANAGED_ENV_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "LOG_FORMAT",
    "LLM_BACKEND",
    "LLM_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "PG_DSN",
    "PG_POOL_MIN_SIZE",
    "PG_POOL_MAX_SIZE",
    "PET_MCP_PROJECT_DIR",
    "PETSTORE_API_BASE_URL",
)


@pytest.fixture(autouse=True)
def isolate_settings() -> Iterator[None]:
    """Clear the settings cache and the service's env vars around each test."""
    saved = {key: os.environ[key] for key in MANAGED_ENV_VARS if key in os.environ}
    for key in MANAGED_ENV_VARS:
        os.environ.pop(key, None)
    get_settings.cache_clear()
    yield
    for key in MANAGED_ENV_VARS:
        os.environ.pop(key, None)
    os.environ.update(saved)
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Default settings, built from no environment at all."""
    return Settings()


@pytest.fixture
def schema_path() -> Path:
    """Path to the schema applied at startup."""
    return Path(__file__).resolve().parent.parent / "init.sql"


@pytest.fixture
async def db_pool() -> Any:
    """A pool against TEST_DATABASE_URL, or skip.

    Point TEST_DATABASE_URL at a disposable database: these tests apply the
    schema and write rows.
    """
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is not set")
    from pet_agent.db import create_pool

    pool = await create_pool(dsn)
    try:
        yield pool
    finally:
        await pool.close()
