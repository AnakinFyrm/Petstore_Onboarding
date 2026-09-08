"""Local stand-in for `fyrm_service_core.envfiles` - see `__init__.py`.

Implements the same three-layer precedence described in `config.py`'s module
docstring: the real process environment always wins, then `.env.$APP_ENV`,
then `.env.shared`; both files are read from the current working directory
only, and under pytest neither is read unless the caller passes
``force=True``.
本文件是 `fyrm_service_core.envfiles` 的本地替代——见 `__init__.py`。

实现的是 `config.py` 模块文档字符串里描述的那套三层优先级:进程本身的真实
环境变量永远优先,然后是 `.env.$APP_ENV`,再然后是 `.env.shared`;两个文件都
只从当前工作目录读取,并且在 pytest 底下,除非调用方传了 ``force=True``,
否则两个文件都不会被读取。
"""

import os
import sys
import warnings
from pathlib import Path


def _running_under_pytest() -> bool:
    """True while collected/run by pytest - checked, not assumed, so a plain
    script import behaves like production.

    是否正在被 pytest 收集/运行——这是实际检查出来的,不是假设出来的,这样
    普通脚本导入这个模块时的行为就跟生产环境一样。
    """
    return "pytest" in sys.modules


def _parse_dotenv(path: Path) -> dict[str, str]:
    """A minimal KEY=value dotenv parser: blank lines and ``#`` comments are
    skipped, and one layer of matching quotes around the value is stripped.

    一个最简单的 KEY=value dotenv 解析器:跳过空行和 ``#`` 注释,并且去掉
    值两边匹配的一层引号。
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env_files(*, force: bool = False) -> str:
    """Load `.env.$APP_ENV` and `.env.shared` into the process environment.

    Returns the resolved ``APP_ENV`` (``"dev"`` when unset). Keys already
    present in ``os.environ`` are never overwritten, and a key declared in
    both files raises a :class:`RuntimeWarning` naming it, on the theory that
    duplication across the two files is almost always a mistake rather than
    an intentional override.

    把 `.env.$APP_ENV` 和 `.env.shared` 加载进进程环境变量。

    返回解析出来的 ``APP_ENV``(没设置时是 ``"dev"``)。已经存在于
    ``os.environ`` 里的键永远不会被覆盖;如果同一个键在两个文件里都出现了,
    会抛出一个点名这个键的 :class:`RuntimeWarning`——这里的假设是,两个文件
    里都写同一个键几乎总是失误,而不是故意的覆盖。
    """
    if _running_under_pytest() and not force:
        return os.environ.get("APP_ENV", "dev")

    app_env = os.environ.get("APP_ENV", "dev")
    cwd = Path.cwd()
    shared = _parse_dotenv(cwd / ".env.shared")
    profile = _parse_dotenv(cwd / f".env.{app_env}")

    overlap = set(shared) & set(profile)
    if overlap:
        names = ", ".join(sorted(overlap))
        warnings.warn(
            f"Key(s) declared in both .env.{app_env} and .env.shared: {names}. Keep each key in exactly one file.",
            RuntimeWarning,
            stacklevel=2,
        )

    # Profile values take priority over shared; setdefault() means neither
    # ever overwrites a value the real process environment already supplied.
    # profile 优先于 shared;用 setdefault() 意味着两者都不会覆盖进程本身已经
    # 有的环境变量值。
    for key, value in {**shared, **profile}.items():
        os.environ.setdefault(key, value)

    return app_env
