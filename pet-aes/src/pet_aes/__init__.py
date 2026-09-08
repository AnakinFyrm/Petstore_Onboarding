"""pet-aes: generic Agentic Enterprise System (AES) building blocks.

Two things live here:

* :mod:`pet_aes.agents` - turn a declarative :class:`~pet_aes.agents.AgentSpec`
  into a ``pydantic_ai.Agent``, with tools resolved by name and MCP toolsets
  filtered to an allow-list.
* :mod:`pet_aes.service` - :class:`~pet_aes.service.HostedAgentService`, the
  operational boundary that runs a built agent for the life of a
  conversation: receives a message, runs the agent, returns the reply, and
  turns any failure into a safe fallback instead of a leaked exception.

Adapted from this organization's reference AES implementation, stripped of
everything specific to that other service, so any project that hosts a
Pydantic AI agent in AES - this one included - can depend on it directly
instead of re-implementing the same pattern.

pet-aes:通用的 Agentic Enterprise System(AES)基础设施。

这里放两样东西:

* :mod:`pet_aes.agents` —— 把一份声明式的
  :class:`~pet_aes.agents.AgentSpec` 变成一个 ``pydantic_ai.Agent``,工具按
  名字解析,MCP toolset 按白名单过滤。
* :mod:`pet_aes.service` —— :class:`~pet_aes.service.HostedAgentService`,
  在一整场对话期间运行一个已经构建好的 agent 的"运行边界":接收消息、运行
  agent、返回回复,任何失败都会被换成一个安全的兜底回复,而不是让异常泄露
  出去。

参照的是组织内部的一个参考 AES 实现,去掉了所有跟那个具体项目绑定的部分,
这样任何要把 Pydantic AI agent 托管进 AES 的项目——包括这一个——都可以直接
依赖它,而不用重新实现一遍同样的模式。
"""

from pet_aes.agents import AgentRegistry, AgentSpec, LocalTool, build_agent, resolve_tools
from pet_aes.service import DEFAULT_FALLBACK_MESSAGE, HostedAgentService

__all__ = [
    "DEFAULT_FALLBACK_MESSAGE",
    "AgentRegistry",
    "AgentSpec",
    "HostedAgentService",
    "LocalTool",
    "build_agent",
    "resolve_tools",
]
