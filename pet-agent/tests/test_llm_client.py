"""LLM client tests, fully offline via pydantic-ai test doubles. Never live calls."""

import pytest

from pet_agent.config import Settings
from pet_agent.llm.client import DEFAULT_ANTHROPIC_MODEL, create_llm, structured_call
from pet_agent.llm.schemas import ExtractedItem

LLM_ENV_VARS = (
    "LLM_BACKEND",
    "LLM_MODEL",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in LLM_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _make_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def test_create_llm_returns_none_for_backend_none(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch, LLM_BACKEND="none")
    assert create_llm(settings) is None


def test_create_llm_returns_none_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for backend in ("anthropic", "openai", "azure"):
        settings = _make_settings(monkeypatch, LLM_BACKEND=backend)
        assert create_llm(settings) is None


def test_create_llm_returns_none_for_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch, LLM_BACKEND="bogus")
    assert create_llm(settings) is None


def test_create_llm_builds_anthropic_model_with_default_name(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch, LLM_BACKEND="anthropic", ANTHROPIC_API_KEY="test-key")
    model = create_llm(settings)
    assert model is not None
    assert model.model_name == DEFAULT_ANTHROPIC_MODEL


def test_create_llm_respects_llm_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(
        monkeypatch, LLM_BACKEND="anthropic", ANTHROPIC_API_KEY="test-key", LLM_MODEL="claude-test"
    )
    model = create_llm(settings)
    assert model is not None
    assert model.model_name == "claude-test"


def test_create_llm_builds_openai_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch, LLM_BACKEND="openai", OPENAI_API_KEY="test-key", LLM_MODEL="gpt-test")
    model = create_llm(settings)
    assert model is not None
    assert model.model_name == "gpt-test"


def test_create_llm_builds_openai_compat_model_from_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(
        monkeypatch,
        LLM_BACKEND="openai_compat",
        OPENAI_BASE_URL="http://localhost:11434/v1",
        LLM_MODEL="local-model",
    )
    model = create_llm(settings)
    assert model is not None
    assert model.model_name == "local-model"


def test_create_llm_builds_azure_model(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(
        monkeypatch,
        LLM_BACKEND="azure",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
        AZURE_OPENAI_DEPLOYMENT="gpt-test",
        AZURE_OPENAI_API_VERSION="2024-06-01",
    )
    model = create_llm(settings)
    assert model is not None
    assert model.model_name == "gpt-test"


def test_structured_call_returns_validated_schema() -> None:
    from pydantic_ai.models.test import TestModel

    model = TestModel(custom_output_args={"name": "widget", "quantity": "3", "unit": "pcs"})
    out = structured_call(model, "system", "user", ExtractedItem)
    assert isinstance(out, ExtractedItem)
    assert out.name == "widget"
    assert out.quantity == "3"
    assert out.date is None


def test_structured_call_returns_none_when_model_fails() -> None:
    from pydantic_ai.messages import ModelMessage, ModelResponse
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    def _boom(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("model exploded")

    # A failing model must degrade to None so callers fall back to deterministic logic.
    assert structured_call(FunctionModel(_boom), "system", "user", ExtractedItem) is None
