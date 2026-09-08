"""Tests for settings validation and the env-file wiring.

The layering rules themselves are pinned in fyrm-service-core's test suite;
here we prove this service is wired to them (one smoke test, plus the pytest
guard that keeps a developer's env files out of test runs) and validate what
is specific to this service's ``Settings``.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from pet_agent.config import Settings, enforce_production_settings, get_settings, load_env_files

# Keys used only by these tests. load_dotenv writes straight into os.environ, so
# they are removed explicitly rather than relying on monkeypatch.
TEST_KEYS = ("PROFILE_TEST_A", "PROFILE_TEST_B", "PROFILE_TEST_C")


@pytest.fixture(autouse=True)
def clean_test_keys() -> Iterator[None]:
    for key in TEST_KEYS:
        os.environ.pop(key, None)
    yield
    for key in TEST_KEYS:
        os.environ.pop(key, None)


def write_env(directory: Path, name: str, **values: str) -> None:
    body = "".join(f"{key}={value}\n" for key, value in values.items())
    (directory / name).write_text(body, encoding="utf-8")


def test_shared_and_profile_both_contribute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    write_env(tmp_path, ".env.test", PROFILE_TEST_A="from-profile")
    write_env(tmp_path, ".env.shared", PROFILE_TEST_B="from-shared")

    assert load_env_files(force=True) == "test"
    assert os.environ["PROFILE_TEST_A"] == "from-profile"
    assert os.environ["PROFILE_TEST_B"] == "from-shared"


def test_env_files_are_not_read_under_pytest_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    write_env(tmp_path, ".env.test", PROFILE_TEST_A="should-not-be-loaded")

    assert load_env_files() == "test"
    assert "PROFILE_TEST_A" not in os.environ


def test_app_env_defaults_to_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    assert load_env_files() == "dev"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


@pytest.mark.parametrize("app_env", ["dev", "development", "local", "test", "testing"])
def test_dev_environments_are_not_production(app_env: str) -> None:
    assert Settings(app_env=app_env).is_production is False


def test_unknown_environment_is_treated_as_production() -> None:
    # Fail safe: an environment nobody listed gets the strict rules, not the lax ones.
    assert Settings(app_env="staging").is_production is True


def test_enforce_production_settings_allows_dev_defaults() -> None:
    enforce_production_settings(Settings(app_env="dev"))


def test_enforce_production_settings_requires_a_configured_llm() -> None:
    with pytest.raises(RuntimeError, match="LLM_BACKEND"):
        enforce_production_settings(Settings(app_env="production", llm_backend="none"))


def test_enforce_production_settings_accepts_a_configured_llm() -> None:
    settings = Settings(
        app_env="production",
        llm_backend="anthropic",
        anthropic_api_key=SecretStr("a-key"),
        pg_dsn="postgresql://user:pass@db:5432/app",
    )
    enforce_production_settings(settings)


def test_pet_mcp_settings_have_sensible_local_dev_defaults() -> None:
    settings = Settings()
    assert settings.pet_mcp_project_dir == "../pet-mcp"
    assert settings.petstore_api_base_url == "http://localhost:8000"


def test_enforce_production_settings_requires_pet_mcp_project_dir() -> None:
    with pytest.raises(RuntimeError, match="PET_MCP_PROJECT_DIR"):
        enforce_production_settings(
            Settings(
                app_env="production",
                llm_backend="anthropic",
                anthropic_api_key=SecretStr("a-key"),
                pg_dsn="postgresql://user:pass@db:5432/app",
                pet_mcp_project_dir="",
            )
        )
