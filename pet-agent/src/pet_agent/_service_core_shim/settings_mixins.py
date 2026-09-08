"""Local stand-in for `fyrm_service_core.settings_mixins` - see `__init__.py`.

These two mixins exist purely to be combined via multiple inheritance into one
`Settings` class, exactly the way `fyrm_service_core`'s originals are used in
`config.py` (``class Settings(AppEnvSettings, LoggingSettings): ...``): each
one owns a small, independent slice of the process's configuration.
本文件是 `fyrm_service_core.settings_mixins` 的本地替代——见 `__init__.py`。

这两个 mixin 存在的唯一目的,就是像 `config.py` 里那样通过多重继承组合成一个
`Settings` 类(``class Settings(AppEnvSettings, LoggingSettings): ...``):
每一个都只负责进程配置里一小块、彼此独立的部分。
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Names treated as "not production" - anything else (an unlisted staging name,
# a typo) is fail-safe production, per this project's own
# test_unknown_environment_is_treated_as_production.
# 被当作"不是生产环境"的名字集合——除此以外的任何名字(没列出来的 staging、
# 打错的字)都会被当成生产环境,失败时偏向更严格的一侧;对应本项目自己的
# test_unknown_environment_is_treated_as_production 这个测试。
_DEV_LIKE_ENVIRONMENTS = frozenset({"dev", "development", "local", "test", "testing"})


class AppEnvSettings(BaseSettings):
    """Which environment this process is running in, and whether that is production."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", populate_by_name=True)

    app_env: str = Field(default="dev", validation_alias="APP_ENV")

    @property
    def is_production(self) -> bool:
        """True for anything not explicitly recognized as a dev-like environment.

        对于任何没有被明确认定为"开发类"环境的名字,都返回 True。
        """
        return self.app_env.strip().lower() not in _DEV_LIKE_ENVIRONMENTS


class LoggingSettings(BaseSettings):
    """Logging verbosity and output shape, shared by every fyrm service."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", populate_by_name=True)

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    # "text" for humans, "json" for log aggregators.
    log_format: str = Field(default="text", validation_alias="LOG_FORMAT")
