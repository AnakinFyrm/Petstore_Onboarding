"""Tests for pet_aes.agents: AgentSpec, the local/MCP tool split, and the
allow-list filtering that bounds an agent's MCP surface.

针对 pet_aes.agents 的测试:AgentSpec、本地工具与 MCP 工具的划分,以及用来
限定一个 agent 的 MCP 能力范围的白名单过滤逻辑。

The MCP-shaped tools here use ``pydantic_ai.toolsets.FunctionToolset`` rather
than a real MCP server - it is the same ``AbstractToolset`` interface
``_filtered_toolsets`` operates on, so it exercises the exact filtering code
path without pulling in fastmcp as a dependency of this package.
这里用来扮演"MCP 工具"的其实是 ``pydantic_ai.toolsets.FunctionToolset``,而
不是一个真正的 MCP 服务器 —— 它实现的是跟 ``_filtered_toolsets`` 打交道的同
一个 ``AbstractToolset`` 接口,所以能原样测到过滤逻辑本身,又不需要让这个包
额外依赖 fastmcp。
"""

from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import Tool
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from pet_aes.agents import AgentRegistry, AgentSpec, LocalTool, build_agent, resolve_tools


@pytest.fixture
def prompt_file(tmp_path: Path) -> Path:
    """A tiny system-prompt file on disk, standing in for a real one.

    磁盘上一个很小的系统提示词文件,代替一个真实的提示词文件。
    """
    path = tmp_path / "system.md"
    path.write_text("You are a test agent. Be concise.", encoding="utf-8")
    return path


@pytest.fixture
def local_tool_registry() -> dict[str, LocalTool]:
    """A tiny local-tool registry: one plain function, keyed by logical name.

    一个很小的本地工具 registry:一个普通函数,按逻辑名字索引。
    """

    def add_numbers(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    return {"add_numbers": add_numbers}


@pytest.fixture
def mcp_like_toolset() -> FunctionToolset:
    """A ``FunctionToolset`` with three tools, standing in for an MCP server
    that (deliberately) exposes more tools than any one agent should have.

    一个带三个工具的 ``FunctionToolset``,用来代替一个(故意)暴露了比任何
    单个 agent 应有权限更多工具的 MCP 服务器。
    """
    toolset = FunctionToolset()

    def search_pets(species: str | None = None) -> list[dict[str, object]]:
        """Search pets, optionally filtered by species."""
        return [{"id": 1, "name": "Luna", "species": "cat"}]

    def get_pet(pet_id: int) -> dict[str, object]:
        """Get one pet's details."""
        return {"id": pet_id, "name": "Luna"}

    def purchase_pet(pet_id: int, confirm: bool = False) -> dict[str, object]:
        """Buy a pet - not declared by any spec in these tests, so it must
        never be reachable no matter which toolset instance carries it.

        买一只宠物 —— 本文件里没有任何 spec 声明过这个工具,所以不管它挂在哪
        个 toolset 实例上,都绝不能被够到。
        """
        return {"id": 99, "pet_id": pet_id, "status": "completed"}

    toolset.add_function(search_pets, name="search_pets")
    toolset.add_function(get_pet, name="get_pet")
    toolset.add_function(purchase_pet, name="purchase_pet")
    return toolset


def test_agent_spec_load_prompt_reads_the_file(prompt_file: Path) -> None:
    spec = AgentSpec(name="test-agent", prompt_path=prompt_file)
    assert spec.load_prompt() == "You are a test agent. Be concise."


def test_agent_spec_load_prompt_raises_a_clear_error_when_missing(tmp_path: Path) -> None:
    spec = AgentSpec(name="test-agent", prompt_path=tmp_path / "missing.md")
    with pytest.raises(FileNotFoundError, match=r"missing\.md"):
        spec.load_prompt()


def test_agent_spec_declared_tools_is_the_union_of_required_and_optional(prompt_file: Path) -> None:
    spec = AgentSpec(
        name="test-agent",
        prompt_path=prompt_file,
        tools=("add_numbers",),
        optional_tools=("search_pets", "get_pet"),
    )
    assert spec.declared_tools == frozenset({"add_numbers", "search_pets", "get_pet"})


def test_resolve_tools_raises_on_an_unknown_name(local_tool_registry: dict[str, LocalTool]) -> None:
    # A typo in a spec's `tools` must fail loudly, not silently run an agent
    # with fewer tools than intended.
    # spec 里 `tools` 的一个笔误必须马上报错,而不是悄悄让 agent 带着比预期
    # 更少的工具跑起来。
    with pytest.raises(KeyError, match="subtract_numbers"):
        resolve_tools(["add_numbers", "subtract_numbers"], local_tool_registry)


def test_resolve_tools_returns_the_matching_instances(local_tool_registry: dict[str, LocalTool]) -> None:
    resolved = resolve_tools(["add_numbers"], local_tool_registry)
    assert resolved == [local_tool_registry["add_numbers"]]


def test_build_agent_raises_on_an_unknown_required_tool_name(
    prompt_file: Path, local_tool_registry: dict[str, LocalTool]
) -> None:
    spec = AgentSpec(name="test-agent", prompt_path=prompt_file, tools=("not_registered",))
    with pytest.raises(KeyError, match="not_registered"):
        build_agent(spec, model=TestModel(), tools=local_tool_registry)


def test_build_agent_skips_a_missing_optional_tool_silently(
    prompt_file: Path, local_tool_registry: dict[str, LocalTool]
) -> None:
    # `not_registered` is optional here, so it is simply absent from the
    # built agent rather than raising - the same behaviour an MCP tool name
    # gets when its server is unreachable at startup.
    # 这里 `not_registered` 是可选的,所以构建出来的 agent 里就只是没有它,
    # 而不是报错 —— 跟一个 MCP 工具名在其服务器启动时连不上时的行为一样。
    spec = AgentSpec(name="test-agent", prompt_path=prompt_file, optional_tools=("not_registered",))
    agent = build_agent(spec, model=TestModel(), tools=local_tool_registry)
    assert agent is not None


async def test_build_agent_wires_local_tools_by_name(
    prompt_file: Path, local_tool_registry: dict[str, LocalTool]
) -> None:
    spec = AgentSpec(name="test-agent", prompt_path=prompt_file, tools=("add_numbers",))
    agent = build_agent(spec, model=TestModel(call_tools="all"), tools=local_tool_registry)
    async with agent:
        result = await agent.run("please add some numbers")
    calls = [p.tool_name for msg in result.all_messages() for p in msg.parts if isinstance(p, ToolCallPart)]
    assert calls == ["add_numbers"]


async def test_build_agent_filters_mcp_like_toolset_to_the_spec_allow_list(
    prompt_file: Path, mcp_like_toolset: FunctionToolset
) -> None:
    # SECURITY: the toolset carries three tools; the spec only declares two.
    # `call_tools="all"` makes TestModel call every tool it can SEE, so if
    # `purchase_pet` is ever called here the allow-list filter has failed.
    # 安全测试:这个 toolset 上挂着三个工具,而 spec 只声明了两个。
    # `call_tools="all"` 会让 TestModel 调用它能看到的每一个工具,所以如果
    # `purchase_pet` 在这里被调用了,就说明白名单过滤失效了。
    spec = AgentSpec(
        name="test-agent",
        prompt_path=prompt_file,
        optional_tools=("search_pets", "get_pet"),
    )
    agent = build_agent(
        spec,
        model=TestModel(call_tools="all"),
        tools={},
        toolsets=[mcp_like_toolset],
    )
    async with agent:
        result = await agent.run("do you have any cats?")
    calls = {p.tool_name for msg in result.all_messages() for p in msg.parts if isinstance(p, ToolCallPart)}
    assert calls == {"search_pets", "get_pet"}
    assert "purchase_pet" not in calls


def test_build_agent_sets_output_type_when_a_schema_is_given(prompt_file: Path) -> None:
    class Reply(BaseModel):
        answer: str

    spec = AgentSpec(name="test-agent", prompt_path=prompt_file, output_schema=Reply)
    agent = build_agent(spec, model=TestModel(), tools={})
    assert agent.output_type is Reply


def test_build_agent_accepts_an_explicit_tool_instance(prompt_file: Path) -> None:
    # `LocalTool` also covers an explicitly-named `pydantic_ai.Tool`, not
    # only a bare function.
    # `LocalTool` 也覆盖显式命名的 `pydantic_ai.Tool`,不只是一个裸函数。
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    named_tool = Tool(multiply, name="multiply")
    spec = AgentSpec(name="test-agent", prompt_path=prompt_file, tools=("multiply",))
    agent = build_agent(spec, model=TestModel(), tools={"multiply": named_tool})
    assert agent is not None


def test_agent_registry_register_rejects_a_duplicate_name(prompt_file: Path) -> None:
    registry = AgentRegistry()
    spec = AgentSpec(name="dup", prompt_path=prompt_file)
    registry.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AgentSpec(name="dup", prompt_path=prompt_file))


def test_agent_registry_contains_and_names(prompt_file: Path) -> None:
    registry = AgentRegistry([AgentSpec(name="a", prompt_path=prompt_file)])
    assert "a" in registry
    assert "b" not in registry
    assert registry.names() == ["a"]


def test_agent_registry_getitem_returns_the_registered_spec(prompt_file: Path) -> None:
    spec = AgentSpec(name="a", prompt_path=prompt_file)
    registry = AgentRegistry([spec])
    assert registry["a"] is spec


def test_agent_registry_build_returns_one_agent_per_requested_name(prompt_file: Path) -> None:
    registry = AgentRegistry([
        AgentSpec(name="a", prompt_path=prompt_file),
        AgentSpec(name="b", prompt_path=prompt_file),
    ])
    agents = registry.build(["a", "b"], model=TestModel(), tools={})
    assert set(agents) == {"a", "b"}
    assert agents["a"].name == "a"
    assert agents["b"].name == "b"
