"""Temporary local stand-in for the private `fyrm-service-core` dependency.

This project could not get read access to `fyrm-ai/fyrm-service-core`
(a private GitHub repo - see ../../../docs/private-dependencies.md), so
`uv sync` cannot clone it. This package reimplements only the exact pieces
this project actually imports from it: `envfiles.load_env_files`,
`settings_mixins.AppEnvSettings`/`LoggingSettings`, and the handful of
`logging_config` names re-exported by `pet_agent/logging_config.py`. Behaviour
is matched against this project's own existing tests
(`tests/test_config.py`, `tests/test_logging_config.py`), which were written
against the real library and were not changed for this swap.

Once you have access to the real repository:
    1. Uncomment `fyrm-service-core[settings]` in `pyproject.toml`'s
       `dependencies`, and the matching `[tool.uv.sources]` entry.
    2. In `config.py` and `logging_config.py`, change the two import lines
       that currently read `from pet_agent._service_core_shim...` back to
       `from fyrm_service_core...`.
    3. Delete this whole `_service_core_shim` package.
    4. Run `uv sync` and the test suite again to confirm nothing changed.

这是私有依赖 `fyrm-service-core` 的一个临时本地替代品。

这个项目暂时拿不到 `fyrm-ai/fyrm-service-core`(一个私有 GitHub 仓库——见
../../../docs/private-dependencies.md)的读权限,所以 `uv sync` 没法把它克隆
下来。这个包只重新实现了本项目真正用到的那几个东西:
`envfiles.load_env_files`、`settings_mixins.AppEnvSettings`/`LoggingSettings`,
以及 `pet_agent/logging_config.py` 重新导出的那几个 `logging_config` 名字。
它们的行为是照着本项目已有的测试(`tests/test_config.py`、
`tests/test_logging_config.py`——这两个文件是针对真实的库写的,这次为了做
这个替换并没有改动它们)对齐的。

等你拿到真实仓库的权限之后:
    1. 把 `pyproject.toml` 的 `dependencies` 里 `fyrm-service-core[settings]`
       那一行,以及对应的 `[tool.uv.sources]` 条目取消注释。
    2. 在 `config.py` 和 `logging_config.py` 里,把现在写着
       `from pet_agent._service_core_shim...` 的那两行导入改回
       `from fyrm_service_core...`。
    3. 删掉整个 `_service_core_shim` 这个包。
    4. 重新跑一次 `uv sync` 和测试套件,确认一切照常。
"""
