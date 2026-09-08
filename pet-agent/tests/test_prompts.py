"""Prompt-loading tests: the Markdown files and the exported constants stay in sync."""

from pathlib import Path

import pet_agent.llm.prompts as prompts


def test_every_md_file_has_a_constant_and_vice_versa() -> None:
    assert prompts.__file__ is not None
    md_stems = {path.stem for path in Path(prompts.__file__).parent.glob("*.md")}
    assert md_stems, "the prompts package must ship at least one .md prompt"
    assert {f"{stem.upper()}_PROMPT" for stem in md_stems} == set(prompts.__all__)
    for name in prompts.__all__:
        value = getattr(prompts, name)
        assert isinstance(value, str)
        assert value.strip()


def test_system_prompt_contains_anti_hallucination_rule() -> None:
    assert "never guess" in prompts.SYSTEM_PROMPT.lower()
    assert prompts.SYSTEM_PROMPT.lstrip().startswith("#")
