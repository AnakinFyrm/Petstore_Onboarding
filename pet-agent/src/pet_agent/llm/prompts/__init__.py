"""System prompts, authored as Markdown files in this package.

Each prompt lives in its own ``.md`` file so it can be read, reviewed and
diffed as prose instead of hiding inside a Python string literal. Prompts are
loaded once at import time and exposed as module constants named
``<STEM>_PROMPT`` (``system.md`` becomes ``SYSTEM_PROMPT``); a test asserts
that the files and the exported constants stay in sync.
"""

from pathlib import Path

_DIR = Path(__file__).parent


def _load(stem: str) -> str:
    return (_DIR / f"{stem}.md").read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = _load("system")

__all__ = ["SYSTEM_PROMPT"]
