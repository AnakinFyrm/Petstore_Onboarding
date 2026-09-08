"""Local stand-in for `fyrm_service_core.logging_config` - see `__init__.py`.

Provides the correlation-id ContextVar, JSON/text output, and
redaction-on-by-default that `pet_agent/logging_config.py` re-exports.
Behaviour is matched against `tests/test_logging_config.py`, which is
unchanged and was written against the real library.
本文件是 `fyrm_service_core.logging_config` 的本地替代——见 `__init__.py`。

提供的是 `pet_agent/logging_config.py` 重新导出的那些东西:correlation-id
的 ContextVar、JSON/文本两种输出格式,以及默认开启的信息屏蔽(redaction)。
行为是照着 `tests/test_logging_config.py`(这个文件没有改动,是针对真实的库
写的)对齐的。
"""

import contextvars
import json
import logging
from collections.abc import Sequence

# One id per run/request, read and set from anywhere without threading it
# through every function call - cli.py sets it once per CLI invocation.
# 每次运行/请求一个 id,不需要在每个函数调用之间手动传递就能读写——cli.py 会
# 在每次命令行调用时设置一次。
_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)

# The attributes a bare LogRecord already carries, computed once so both
# JsonFormatter (what to include) and this module's authors (what NOT to
# scan for secrets) have one source of truth for "extra, application-added
# field" versus "standard logging machinery field".
# 一个"空白"LogRecord 本来就带的属性集合,只算一次;这样 JsonFormatter(该带
# 上哪些字段)和这个模块本身,对于"应用自己加的额外字段"和"logging 自带的
# 标准字段"就有了同一个判断标准。
_STANDARD_LOG_RECORD_KEYS = frozenset(
    logging.LogRecord("probe", logging.INFO, __file__, 1, "probe", None, None).__dict__.keys()
) | {"correlation_id"}

# Substrings matched case-insensitively against an extra field's *name* (not
# its value) - deliberately broad, since missing a secret is worse than
# redacting an innocent field named e.g. "token_count".
# 按大小写不敏感的方式,匹配额外字段*名字*(不是它的值)里的子串——故意写得
# 宽松一点,因为漏掉一个真正的密钥,比误伤一个恰好叫 "token_count" 的无害字段
# 后果更严重。
_DEFAULT_REDACTED_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "dsn",
    "authorization",
    "credential",
    "private_key",
)


def get_correlation_id() -> str | None:
    """Read the current run's correlation id, or ``None`` outside any run."""
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> None:
    """Set the current run's correlation id; pass ``None`` to clear it."""
    _correlation_id.set(value)


class CorrelationFilter(logging.Filter):
    """Stamps every record with the current correlation id (or ``"-"``).

    给每一条日志记录都打上当前的 correlation id(没有时就是 ``"-"``)。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id() or "-"
        return True


class RedactionFilter(logging.Filter):
    """Blanks out extra fields whose *name* looks secret-shaped.

    把名字看起来像密钥的额外字段的值抹掉。

    On by default with a fixed set of common secret-ish key-name substrings;
    a call site can widen that set for its own vocabulary via
    ``setup_logging(redact_keys=[...])``.
    默认就会启用,内置了一组常见的、看起来像密钥的字段名子串;调用方可以通过
    ``setup_logging(redact_keys=[...])`` 针对自己项目的用词再扩充这个集合。
    """

    def __init__(self, *, extra_keys: Sequence[str] | None = None) -> None:
        super().__init__()
        self._patterns = tuple(_DEFAULT_REDACTED_KEY_SUBSTRINGS) + tuple(key.lower() for key in (extra_keys or ()))

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in list(record.__dict__.items()):
            if isinstance(value, str) and any(pattern in key.lower() for pattern in self._patterns):
                record.__dict__[key] = "[redacted]"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per log line, for log aggregators.

    每一行日志就是一个 JSON 对象,给日志聚合系统用。
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None) or get_correlation_id() or "-",
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_KEYS:
                payload[key] = value
        # default=str: an extra field that is not JSON-native (a Path, an
        # enum, ...) becomes its str() rather than raising mid-log-call.
        # default=str:一个本身不是 JSON 原生类型的额外字段(比如 Path、
        # enum……)会被转成它的 str(),而不是在打日志的时候直接抛异常。
        return json.dumps(payload, default=str)


def setup_logging(*, level: str = "INFO", log_format: str = "text", redact_keys: Sequence[str] | None = None) -> None:
    """Configure the root logger: one stream handler, correlation id, redaction on.

    配置根 logger:一个流式 handler,带 correlation id,默认开启信息屏蔽。

    Replaces any handlers already on the root logger, so calling this twice
    (e.g. once in a test, once in the real entry point) never doubles output.
    会替换掉根 logger 已有的所有 handler,所以重复调用这个函数(比如测试里调
    一次、真正的入口再调一次)不会让日志输出重复。
    """
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers[:] = []

    handler = logging.StreamHandler()
    if log_format.strip().lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(correlation_id)s] %(name)s: %(message)s")
        )
    handler.addFilter(CorrelationFilter())
    handler.addFilter(RedactionFilter(extra_keys=redact_keys))
    root.addHandler(handler)
