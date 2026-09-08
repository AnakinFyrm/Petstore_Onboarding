"""Logging for this service.

The implementation — text/json output, the correlation-id ContextVar, and
redaction on by default — normally lives in ``fyrm_service_core.logging_config``
and is re-exported here so application code keeps one import path. Change
behaviour in the library; extend the redacted keys per call with
``setup_logging(redact_keys=[...])``.

TEMPORARY: the import below points at a local stand-in
(``pet_agent._service_core_shim``) instead, because this checkout does not
have read access to that private repo yet — see
``src/pet_agent/_service_core_shim/__init__.py`` for why and how to switch
back once access is available. Nothing else in this module, or in any of its
callers, needs to change either way.
临时:下面这行导入指向的是一个本地替代实现(``pet_agent._service_core_shim``),
而不是那个私有仓库,因为这份代码检出目前还没有它的读权限——原因和"以后拿到
权限该怎么改回去",见 ``src/pet_agent/_service_core_shim/__init__.py``。不管
是哪种情况,本模块以及它的调用方都不需要再改任何其他东西。
"""

from pet_agent._service_core_shim.logging_config import (
    CorrelationFilter,
    JsonFormatter,
    RedactionFilter,
    get_correlation_id,
    set_correlation_id,
    setup_logging,
)

__all__ = [
    "CorrelationFilter",
    "JsonFormatter",
    "RedactionFilter",
    "get_correlation_id",
    "set_correlation_id",
    "setup_logging",
]
