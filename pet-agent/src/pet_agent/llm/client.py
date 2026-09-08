"""LLM provider factory and a thin structured-output helper, built on Pydantic AI.

``create_llm`` turns the configured backend (``LLM_BACKEND``) into a Pydantic AI
model instance. Pydantic AI is imported lazily inside the builders so the rest
of the package imports, and the deterministic unit tests run, even when no LLM
backend is configured. Nothing in this module raises: a missing or broken
backend logs a warning and returns ``None`` so callers degrade gracefully.

``structured_call`` wraps a model in a one-shot :class:`pydantic_ai.Agent`
whose ``output_type`` is the requested schema, so Pydantic AI enforces the
structured (tool-call) response and validates it. There is no manual JSON
parsing.
"""

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from pet_agent.config import Settings

if TYPE_CHECKING:
    from pydantic_ai.models import Model

    # The model object passed between the agent, tools, and this module.
    LLMModel = Model
else:  # real runtime binding so lazy annotations resolve; mypy uses Model above.
    LLMModel = Any

log = logging.getLogger(__name__)

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"


def create_llm(settings: Settings) -> LLMModel | None:
    """Build the Pydantic AI model for the configured backend.

    Returns ``None`` when the LLM is disabled, unknown, or misconfigured.
    Never raises: callers must be able to run without an LLM.
    """
    if not settings.llm_enabled:
        return None
    backend = settings.llm_backend.lower()
    try:
        if backend == "anthropic":
            return _build_anthropic(settings)
        if backend in {"openai", "openai_compat"}:
            return _build_openai(settings)
        if backend == "azure":
            return _build_azure(settings)
    except Exception as e:
        log.warning("LLM backend %r unavailable: %s", backend, e)
        return None
    log.warning("Unknown LLM_BACKEND=%r; LLM disabled", backend)
    return None


def _build_anthropic(settings: Settings) -> LLMModel:
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    if settings.anthropic_api_key is None:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    return AnthropicModel(
        settings.llm_model or DEFAULT_ANTHROPIC_MODEL,
        provider=AnthropicProvider(api_key=settings.anthropic_api_key.get_secret_value()),
    )


def _build_openai(settings: Settings) -> LLMModel:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if not settings.llm_model:
        raise ValueError("LLM_MODEL is not set")
    if settings.openai_api_key is None and not settings.openai_base_url:
        raise ValueError("OPENAI_API_KEY (or OPENAI_BASE_URL for a compatible gateway) is not set")
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else "not-needed"
    provider_kwargs: dict[str, Any] = {"api_key": api_key}
    if settings.openai_base_url:
        provider_kwargs["base_url"] = settings.openai_base_url
    return OpenAIChatModel(settings.llm_model, provider=OpenAIProvider(**provider_kwargs))


def _build_azure(settings: Settings) -> LLMModel:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.azure import AzureProvider

    if not settings.azure_openai_endpoint or not settings.azure_openai_deployment:
        raise ValueError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT must be set")
    if settings.azure_openai_api_key is None:
        raise ValueError("AZURE_OPENAI_API_KEY is not set")
    return OpenAIChatModel(
        settings.azure_openai_deployment,
        provider=AzureProvider(
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_api_key.get_secret_value(),
        ),
    )


def structured_call[T: BaseModel](llm: LLMModel, system: str, user: str, schema: type[T]) -> T | None:
    """Force a structured (schema-validated) response via a one-shot Pydantic AI agent.

    Returns ``None`` on any failure so callers can fall back to deterministic
    logic instead of handling provider-specific exceptions.
    """
    from pydantic_ai import Agent

    try:
        agent: Agent[None, T] = Agent(llm, output_type=schema, system_prompt=system)
        output = agent.run_sync(user).output
        result = output if isinstance(output, schema) else schema.model_validate(output)
    except Exception as e:
        log.warning("Structured LLM call failed (%s): %s", schema.__name__, e)
        return None
    return result
