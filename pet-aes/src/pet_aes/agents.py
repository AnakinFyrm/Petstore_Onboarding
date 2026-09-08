"""Generic, domain-agnostic agent infrastructure.

This is the one place that knows *how* to turn a declarative :class:`AgentSpec`
(prompt + tool names + output contract) into a runnable :class:`pydantic_ai.Agent`.
An application declares its agent specs once, registers them in an
:class:`AgentRegistry`, and calls :meth:`AgentRegistry.build` (or
:func:`build_agent` directly for a single agent) - it never constructs
``pydantic_ai.Agent`` itself. That is the whole point of this module: it is
the "operational boundary" ONBOARDING.md's Step 7 describes, expressed as
code rather than just a convention someone has to remember.

Two consequences of building agents this way are worth knowing:

* **The output contract is enforced by the framework.** ``spec.output_schema``
  becomes ``output_type``, so the model's answer is validated against the
  pydantic model and re-prompted on failure, up to ``retries``.
* **Tools come from two places, and the split is deliberate.** Local tools
  (plain Python callables) are resolved by name from a registry the caller
  supplies. MCP tools arrive as *toolsets* and are filtered down to exactly
  the names the spec declares - an allow-list enforced on the toolset
  itself, not by whoever happens to build the agent. This is what keeps an
  agent from acquiring a capability just because its MCP server happened to
  be connected and exposed 73 more tools than the agent was meant to have.

一个通用的、跟具体业务无关的 agent 基础设施。

本模块是唯一知道"怎么把一份声明式的 :class:`AgentSpec`(提示词 + 工具名字 +
输出约束)变成一个可运行的 :class:`pydantic_ai.Agent`"的地方。应用只需要
声明一次自己的 agent spec、注册进 :class:`AgentRegistry`,然后调用
:meth:`AgentRegistry.build`(或者对单个 agent 直接调用 :func:`build_agent`)——
应用自己永远不直接构造 ``pydantic_ai.Agent``。这正是本模块的意义所在:它就是
ONBOARDING.md 第 7 步说的那个"运行边界(operational boundary)",只不过是用
代码表达出来,而不是一条只能靠人记住的约定。

这种构建方式有两个值得注意的后果:

* **输出约束是由这个框架强制执行的。**``spec.output_schema`` 会变成
  ``output_type``,所以模型的回答会针对这个 pydantic 模型做校验,校验失败会
  被重新提示(re-prompt),最多 ``retries`` 次。
* **工具来自两个地方,而且这种划分是故意的。** 本地工具(普通的 Python
  可调用对象)按名字从调用方提供的 registry 里查找。MCP 工具则是以
  *toolset* 的形式传进来,并被过滤到只剩 spec 里声明的那几个名字——这是一道
  加在 toolset 本身上的白名单,而不是靠"构建 agent 的人自觉遵守"。这也正是
  为什么一个 agent 不会仅仅因为它连上的 MCP 服务器额外多暴露了 73 个工具,
  就顺带获得了那些工具的能力。

Adapted from this organization's reference AES implementation (a real,
already-running internal service); this version keeps the same
:class:`AgentSpec`/:class:`AgentRegistry`/:func:`build_agent` shape, stripped
of everything specific to that other service, so it stays reusable here and
in any future project that hosts a Pydantic AI agent in AES.
参照的是组织内部一个已经在真实运行的 AES 参考实现;这个版本保留了同样的
:class:`AgentSpec`/:class:`AgentRegistry`/:func:`build_agent` 结构,去掉了
所有跟那个具体项目绑定的部分,这样它才能在这里、以及未来任何一个要把
Pydantic AI agent 托管进 AES 的项目里被复用。
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.models import Model
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset

from pet_aes.helper import load_text

# A local tool is either an explicitly-named Tool or a plain function whose name
# and schema pydantic-ai derives from the signature and docstring.
# 一个本地工具要么是显式命名的 Tool,要么就是一个普通函数——名字和参数结构由
# pydantic-ai 从函数签名和 docstring 里自动推断出来。
LocalTool = Tool[Any] | Callable[..., Any]

# One repair attempt on an output that fails validation: re-prompt the model
# with the validation error rather than silently accepting whatever it said.
# 输出校验失败时允许模型自我修正一次:把校验错误重新喂给模型,而不是悄悄接受
# 一个不符合约束的回答。
DEFAULT_OUTPUT_RETRIES = 1


@dataclass(frozen=True)
class AgentSpec:
    """Everything that defines one agent, in one place.

    一个 agent 的全部定义,都在这一个地方。

    Attributes:
        name: Stable identifier (also the agent's runtime name).
            稳定的标识符(同时也是 agent 运行时的名字)。
        prompt_path: File holding the system prompt.
            存放系统提示词的文件路径。
        tools: Logical local-tool names resolved against the tool registry at
            build time. A missing name is an error - a typo in a spec must
            fail loudly, not silently run an agent with fewer tools than
            intended.
            在构建时,会按名字从本地工具 registry 里解析的逻辑工具名。名字查
            不到就是错误——spec 里的一个笔误必须马上报错,而不是悄悄让 agent
            带着比预期更少的工具跑起来。
        optional_tools: Tool names included only if available, and skipped
            silently otherwise. Use for tools that exist only in some
            deployments - chiefly MCP tools, which are injected at startup
            and absent when their server is unreachable.
            只有在存在时才会被包含、否则悄悄跳过的工具名。用来放那些只在部分
            部署环境里才存在的工具——主要就是 MCP 工具,它们是在启动时被注入
            的,服务器连不上时就会缺失。
        output_schema: Optional pydantic model the agent's output must match.
            agent 输出必须符合的、可选的 pydantic 模型。
        description: Used when this agent is described to another agent.
            当这个 agent 需要被介绍给另一个 agent 时使用。
        subagents: Reserved; unused today.
            预留字段;目前未使用。
    """

    name: str
    prompt_path: Path
    tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    output_schema: type[BaseModel] | None = None
    description: str = ""
    subagents: tuple[str, ...] = ()

    def load_prompt(self) -> str:
        return load_text(self.prompt_path)

    @property
    def declared_tools(self) -> frozenset[str]:
        """Every tool name this spec may hold - the allow-list MCP toolsets are filtered to.

        这个 spec 可能持有的所有工具名——MCP toolset 就是被过滤到只剩这个
        白名单。
        """
        return frozenset(self.tools) | frozenset(self.optional_tools)


def resolve_tools(names: Sequence[str], registry: Mapping[str, LocalTool]) -> list[LocalTool]:
    """Look up tool instances by name, failing loudly on an unknown name.

    按名字查找工具实例;名字不认识就明确报错,而不是悄悄忽略。
    """
    missing = [n for n in names if n not in registry]
    if missing:
        raise KeyError(f"Unknown tool name(s): {', '.join(missing)}. Registered tools: {sorted(registry)}")
    return [registry[n] for n in names]


def _resolve_tools_for(spec: AgentSpec, registry: Mapping[str, LocalTool]) -> list[LocalTool]:
    """Required tools (must exist) + optional tools (included only if present)."""
    resolved = resolve_tools(spec.tools, registry)
    resolved.extend(registry[n] for n in spec.optional_tools if n in registry)
    return resolved


def _filtered_toolsets(spec: AgentSpec, toolsets: Sequence[AbstractToolset[Any]]) -> list[AbstractToolset[Any]]:
    """Each toolset narrowed to the names this spec declares.

    把每一个 toolset 都收窄到只剩这个 spec 声明过的那些名字。

    SECURITY: this is where an agent's MCP surface is bounded. A toolset
    carrying more tools than the spec asks for is filtered down here, so an
    agent cannot acquire a tool merely because its server happened to be
    connected.
    安全边界:一个 agent 能碰到的 MCP 能力范围,就是在这里被限定住的。一个
    toolset 就算实际带着比 spec 要求更多的工具,也会在这里被过滤掉——所以一
    个 agent 不会仅仅因为它的服务器连上了,就顺带获得了本不该有的工具。
    """
    allowed = spec.declared_tools

    def _allow(_ctx: RunContext[Any], tool_def: ToolDefinition) -> bool:
        return tool_def.name in allowed

    return [ts.filtered(_allow) for ts in toolsets]


def build_agent(
    spec: AgentSpec,
    *,
    model: Model,
    tools: Mapping[str, LocalTool],
    toolsets: Sequence[AbstractToolset[Any]] = (),
    retries: int = DEFAULT_OUTPUT_RETRIES,
    deps_type: type | None = None,
) -> Agent[Any, Any]:
    """Build one agent from its spec.

    按一个 spec 构建出一个 agent。

    ``tools`` is the name→instance registry of LOCAL tools; pass ``{}`` for an
    agent (like the Petstore assistant) whose only capabilities come from an
    MCP toolset.
    ``tools`` 是本地工具的"名字 -> 实例"registry;对于一个所有能力都来自 MCP
    toolset 的 agent(比如 Petstore 助手),传 ``{}`` 就行。
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "tools": _resolve_tools_for(spec, tools),
        "toolsets": _filtered_toolsets(spec, toolsets),
        "instructions": spec.load_prompt(),
        "name": spec.name,
        "retries": retries,
    }
    if spec.output_schema is not None:
        kwargs["output_type"] = spec.output_schema
    if deps_type is not None:
        kwargs["deps_type"] = deps_type
    return Agent(**kwargs)


class AgentRegistry:
    """A name -> :class:`AgentSpec` registry with a single ``build`` entrypoint.

    一个"名字 -> :class:`AgentSpec`"的 registry,只有一个 ``build`` 入口。
    """

    def __init__(self, specs: Iterable[AgentSpec] = ()) -> None:
        self._specs: dict[str, AgentSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: AgentSpec) -> AgentSpec:
        if spec.name in self._specs:
            raise ValueError(f"Agent {spec.name!r} is already registered.")
        self._specs[spec.name] = spec
        return spec

    def __getitem__(self, name: str) -> AgentSpec:
        return self._specs[name]

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def names(self) -> list[str]:
        return list(self._specs)

    def build(
        self,
        names: Sequence[str],
        *,
        model: Model,
        tools: Mapping[str, LocalTool],
        toolsets: Sequence[AbstractToolset[Any]] = (),
        retries: int = DEFAULT_OUTPUT_RETRIES,
        deps_type: type | None = None,
    ) -> dict[str, Agent[Any, Any]]:
        """Build several agents at once -> ``{name: agent}``."""
        return {
            name: build_agent(
                self._specs[name],
                model=model,
                tools=tools,
                toolsets=toolsets,
                retries=retries,
                deps_type=deps_type,
            )
            for name in names
        }


__all__ = [
    "DEFAULT_OUTPUT_RETRIES",
    "AgentRegistry",
    "AgentSpec",
    "LocalTool",
    "build_agent",
    "resolve_tools",
]
