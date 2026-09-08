"""Small, dependency-free helpers shared across pet-aes.

跨 pet-aes 内部共用的、不依赖任何其他东西的小工具函数。
"""

from pathlib import Path


def load_text(path: str | Path) -> str:
    """Read a UTF-8 text file, raising a clear error if it is missing.

    读取一个 UTF-8 文本文件,文件不存在时抛出一个说明清楚的错误。
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text(encoding="utf-8")
