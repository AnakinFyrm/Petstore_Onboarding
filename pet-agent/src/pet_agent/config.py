"""Runtime configuration: env-file layering plus one validated settings object.

Configuration arrives from three layers, highest priority first:

    1. the real process environment (``export``, ``docker run -e``, compose)
    2. ``.env.$APP_ENV``   the selected profile: dev | test | production
    3. ``.env.shared``     committed non-secret defaults shared by all profiles

``APP_ENV`` itself is read from the real process environment only, so a dotenv
file can never change which profile is loaded. A personal ``.env`` is
deliberately never read: a file that silently differs between developer
machines is a debugging trap. Files are read from the current working directory
only, so an unrelated ``.env`` further up the tree cannot leak in.

Declaring the same key in both the profile and the shared file is almost always
a mistake, so it raises a :class:`RuntimeWarning` naming the key rather than
silently picking a winner.

Under pytest the files are not read at all unless a test explicitly passes
``force=True``, so a developer's local configuration can never influence a test
run.

The layering implementation lives in fyrm-service-core (``envfiles``); this
module owns parsing and validating the resulting process environment.
"""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

# The aliases are mypy's explicit re-export form: tests and application code
# keep importing these names from here.
#
# TEMPORARY: these two lines point at a local stand-in instead of
# fyrm_service_core, because this checkout does not have read access to that
# private repo yet. See src/pet_agent/_service_core_shim/__init__.py for why
# and for the two-line change to switch back once access is available.
# 临时:下面这两行指向一个本地替代实现,而不是 fyrm_service_core,因为这份
# 代码检出目前还没有那个私有仓库的读权限。原因和"以后拿到权限该怎么改回去"
# (只需要改这两行),都写在
# src/pet_agent/_service_core_shim/__init__.py 里。
from pet_agent._service_core_shim.envfiles import load_env_files as load_env_files
from pet_agent._service_core_shim.settings_mixins import AppEnvSettings, LoggingSettings


class Settings(AppEnvSettings, LoggingSettings):
    """Process configuration, read once and cached by :func:`get_settings`.

    The standard fields (``APP_ENV``, ``LOG_LEVEL``, ``LOG_FORMAT``) and the
    ``is_production`` switch come from the fyrm-service-core mixins; this class
    adds what is specific to this service.
    """

    # No env_file here on purpose: load_env_files() owns reading files, this
    # class owns parsing and validating the resulting process environment.
    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # Identifies this process in telemetry and logs. Override when several
    # deployments of the same code need to be told apart.
    service_name: str = Field(default="pet-agent", validation_alias="SERVICE_NAME")

    # Telemetry is token-gated: without LOGFIRE_TOKEN nothing is configured and
    # nothing leaves the process. TELEMETRY_ENABLED=false forces it off even when
    # a token is present.
    telemetry_enabled: bool = Field(default=True, validation_alias="TELEMETRY_ENABLED")
    logfire_token: SecretStr | None = Field(default=None, validation_alias="LOGFIRE_TOKEN")

    # anthropic | openai | openai_compat | azure | none
    llm_backend: str = Field(default="none", validation_alias="LLM_BACKEND")
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")

    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    azure_openai_api_key: SecretStr | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(default=None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str | None = Field(default=None, validation_alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-10-21", validation_alias="AZURE_OPENAI_API_VERSION")

    pg_dsn: str | None = Field(default=None, validation_alias="PG_DSN")
    pg_pool_min_size: int = Field(default=1, ge=1, validation_alias="PG_POOL_MIN_SIZE")
    pg_pool_max_size: int = Field(default=5, ge=1, validation_alias="PG_POOL_MAX_SIZE")

    # A container often starts before the database accepts connections, so the
    # first connection is retried instead of crashing the process.
    pg_connect_attempts: int = Field(default=10, ge=1, validation_alias="PG_CONNECT_ATTEMPTS")
    pg_connect_backoff_seconds: float = Field(default=1.0, gt=0, validation_alias="PG_CONNECT_BACKOFF_SECONDS")

    # Path (relative to this process's working directory, or absolute) to the
    # pet-mcp project this agent launches as a stdio subprocess and talks to
    # over MCP. This process never imports pet_mcp or pet_client and never
    # calls petstore-api directly - it only knows how to start this one
    # process and speak the MCP protocol to it, which is what keeps
    # "Agent 通过 MCP 服务器操作,不直接访问 Petstore 客户端/数据库"
    # (ONBOARDING.md 第 6/10 节) true in the code, not just in a document.
    # (相对于本进程当前工作目录的、或者绝对的)pet-mcp 项目路径。本 agent 会把
    # 它当作一个 stdio 子进程启动,并通过 MCP 协议跟它对话。这个进程从来不会
    # import pet_mcp 或 pet_client,也从来不会直接调用 petstore-api —— 它只知道
    # 怎么启动这一个进程、怎么讲 MCP 协议,这正是让"Agent 通过 MCP 服务器操作,
    # 不直接访问 Petstore 客户端/数据库"(ONBOARDING.md 第 6/10 节)这条边界在
    # 代码层面成立、而不只是写在文档里的原因。
    pet_mcp_project_dir: str = Field(default="../pet-mcp", validation_alias="PET_MCP_PROJECT_DIR")

    # Passed straight through as PETSTORE_API_BASE_URL in the pet-mcp
    # subprocess's environment; this process itself never talks to
    # petstore-api.
    # 原样透传给 pet-mcp 子进程,作为它的 PETSTORE_API_BASE_URL 环境变量;这个
    # 进程自己从来不会直接跟 petstore-api 通信。
    petstore_api_base_url: str = Field(default="http://localhost:8000", validation_alias="PETSTORE_API_BASE_URL")

    @property
    def llm_enabled(self) -> bool:
        """True only when the selected backend has all the settings it needs.

        Collapsing "disabled" and "misconfigured" into one state keeps the
        service in a single, safe degraded mode instead of crashing at the first
        LLM call.
        """
        backend = self.llm_backend.strip().lower()
        if backend == "anthropic":
            return self.anthropic_api_key is not None
        if backend in {"openai", "openai_compat"}:
            return bool(self.llm_model) and (self.openai_api_key is not None or bool(self.openai_base_url))
        if backend == "azure":
            return all((
                self.azure_openai_api_key is not None,
                self.azure_openai_endpoint,
                self.azure_openai_deployment,
            ))
        return False


def enforce_production_settings(settings: Settings) -> None:
    """Refuse to run with unsafe configuration in production.

    A service that boots unconfigured in production is worse than one that
    refuses to boot, so this raises with every problem listed at once.
    """
    if not settings.is_production:
        return
    problems: list[str] = []
    if not settings.pg_dsn:
        problems.append("PG_DSN must be set")
    if not settings.llm_enabled:
        problems.append(f"LLM_BACKEND={settings.llm_backend!r} is not fully configured")
    if not settings.pet_mcp_project_dir:
        problems.append("PET_MCP_PROJECT_DIR must be set")
    if problems:
        detail = "; ".join(problems)
        raise RuntimeError(f"Refusing to start with APP_ENV={settings.app_env!r}: {detail}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings, loading the env files on first use."""
    load_env_files()
    return Settings()
