"""Agent tests, fully offline.

The model is pydantic-ai's ``TestModel`` (no network call, deterministic).
The "MCP server" is an in-process ``fastmcp.FastMCP`` instance with fake
tools shaped like pet-mcp's real ones - passing a ``FastMCP`` instance
straight to ``MCPToolset`` is pydantic-ai's own documented pattern for
in-process testing, so there is no real subprocess, no real pet-mcp, and no
real petstore-api involved anywhere in this file.
本文件里的测试全部离线运行。模型用的是 pydantic-ai 自带的 ``TestModel``
(不发网络请求,行为确定可重复)。"MCP 服务器"则是一个进程内的
``fastmcp.FastMCP`` 实例,里面装的是几个跟 pet-mcp 真实工具同名同形状的假
工具 —— 把一个 ``FastMCP`` 实例直接传给 ``MCPToolset`` 正是 pydantic-ai 官方
文档里给出的"进程内测试"写法,所以这里没有真正的子进程、没有真正的
pet-mcp,也没有真正的 petstore-api 参与。
"""

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic_ai import capture_run_messages
from pydantic_ai.exceptions import UserError
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.test import TestModel

from pet_agent.agent import build_agent, build_hosted_service, build_pet_mcp_toolset, run_agent
from pet_agent.config import Settings, get_settings


@pytest.fixture
def fake_pet_mcp() -> MCPToolset:
    """An in-process stand-in for pet-mcp, with the same tool names and shapes.

    进程内的 pet-mcp 替身,工具名字和形状都跟真实的一样。
    """
    server = FastMCP("fake-pet-mcp")

    @server.tool()
    def pet_mcp_search_pets(species: str | None = None) -> list[dict[str, object]]:
        """Search pets, optionally filtered by species."""
        return [{"id": 1, "name": "Luna", "species": "cat", "price": 250.0, "availability": "available"}]

    @server.tool()
    def pet_mcp_get_pet(pet_id: int) -> dict[str, object]:
        """Get one pet's current details."""
        return {"id": pet_id, "name": "Luna", "species": "cat", "price": 250.0, "availability": "available"}

    @server.tool()
    def pet_mcp_purchase_pet(pet_id: int, confirm: bool = False) -> dict[str, object]:
        """Buy one pet - only once the customer has explicitly confirmed."""
        if not confirm:
            # Mirrors pet-mcp's own real confirmation gate and error wording,
            # so a test exercising this tool sees the same shape of failure a
            # real run against pet-mcp would.
            # 跟 pet-mcp 真实的确认门槛和报错文案保持一致,这样跑到这个工具的
            # 测试看到的失败形状,跟真正对接 pet-mcp 时是一样的。
            raise ToolError("CONFIRMATION_REQUIRED: ask the customer to confirm before buying.")
        return {"id": 99, "pet_id": pet_id, "status": "completed"}

    return MCPToolset(server)


@pytest.fixture
def fake_pet_mcp_with_extra_tool() -> MCPToolset:
    """Like ``fake_pet_mcp``, plus one extra tool PETSTORE_AGENT_SPEC never declares.

    跟 ``fake_pet_mcp`` 一样,但多了一个 PETSTORE_AGENT_SPEC 从来没声明过的
    额外工具。

    Stands in for pet-mcp exposing more tools in the future than this agent
    is meant to have - used only by the allow-list test below, kept separate
    from ``fake_pet_mcp`` so every other test still reflects exactly the
    three tools pet-mcp really has today.
    代表 pet-mcp 以后可能会暴露出比这个 agent 应有权限更多的工具 —— 只给下面
    那个白名单测试用,跟 ``fake_pet_mcp`` 分开,这样其他测试反映的仍然是
    pet-mcp 今天真正拥有的那三个工具。
    """
    server = FastMCP("fake-pet-mcp-with-extra-tool")

    @server.tool()
    def pet_mcp_search_pets(species: str | None = None) -> list[dict[str, object]]:
        """Search pets, optionally filtered by species."""
        return [{"id": 1, "name": "Luna", "species": "cat", "price": 250.0, "availability": "available"}]

    @server.tool()
    def pet_mcp_get_pet(pet_id: int) -> dict[str, object]:
        """Get one pet's current details."""
        return {"id": pet_id, "name": "Luna", "species": "cat", "price": 250.0, "availability": "available"}

    @server.tool()
    def pet_mcp_delete_pet(pet_id: int) -> dict[str, object]:
        """Not part of pet-mcp's real API and not declared by PETSTORE_AGENT_SPEC -
        must never be reachable no matter what this fake server exposes."""
        return {"id": pet_id, "status": "deleted"}

    return MCPToolset(server)


def _read_only_test_model() -> TestModel:
    """A TestModel restricted to the safe, side-effect-free tools.

    一个被限制只调用安全、无副作用工具的 TestModel。

    ``TestModel`` calls every available tool by default, including ones with
    defaulted arguments - that would call ``pet_mcp_purchase_pet`` with
    ``confirm=False`` and exhaust the agent's retries on the resulting
    ``ToolError``. Restricting ``call_tools`` keeps these tests focused on
    wiring (does the agent reach pet-mcp's tools at all?) rather than on the
    model's own tool-choice behaviour, which ``TestModel`` cannot represent
    meaningfully anyway.
    ``TestModel`` 默认会调用所有可用工具,包括带默认参数的那些 —— 这会用
    ``confirm=False`` 去调 ``pet_mcp_purchase_pet``,进而在随之而来的
    ``ToolError`` 上把 agent 的重试次数耗尽。限定 ``call_tools`` 让这些测试
    只关注"接线是否正确"(agent 到底能不能连到 pet-mcp 的工具),而不是模型
    自己选工具的行为 —— 这一点 ``TestModel`` 本来就没法有意义地模拟。
    """
    return TestModel(call_tools=["pet_mcp_search_pets", "pet_mcp_get_pet"])


async def test_agent_answers_offline(fake_pet_mcp: MCPToolset) -> None:
    agent = build_agent(_read_only_test_model(), fake_pet_mcp)
    result = await agent.run("do you have any cats?")
    assert isinstance(result.output, str)
    assert result.output


async def test_agent_calls_pet_mcp_tools(fake_pet_mcp: MCPToolset) -> None:
    """The agent reaches pet-mcp's tools, not some other, ad-hoc capability."""
    agent = build_agent(_read_only_test_model(), fake_pet_mcp)
    with capture_run_messages() as messages:
        await agent.run("do you have any cats?")
    called = {part.tool_name for message in messages for part in message.parts if isinstance(part, ToolCallPart)}
    assert called & {"pet_mcp_search_pets", "pet_mcp_get_pet"}


async def test_agent_never_acquires_a_tool_pet_mcp_spec_does_not_declare(
    fake_pet_mcp_with_extra_tool: MCPToolset,
) -> None:
    """SECURITY: pet_aes.build_agent filters the toolset to PETSTORE_AGENT_SPEC's allow-list.

    安全测试:pet_aes.build_agent 会把 toolset 过滤到 PETSTORE_AGENT_SPEC 的
    白名单。

    The fake server here exposes a fourth tool, ``pet_mcp_delete_pet``, that
    PETSTORE_AGENT_SPEC never declares. Asking ``TestModel`` to call it raises
    ``UserError: ... configured to call unknown tool ...`` precisely because
    the built agent's toolset has already been filtered down to the three
    names the spec does declare - the model never even sees this tool exists.
    If the allow-list filter ever failed to keep up with pet-mcp exposing more
    tools than intended, this call would succeed instead of raising, and this
    test would catch that.
    这里的假服务器多暴露了第四个工具 ``pet_mcp_delete_pet``,PETSTORE_AGENT_SPEC
    从来没有声明过它。让 ``TestModel`` 去调用它会抛出
    ``UserError: ... configured to call unknown tool ...``——正是因为构建出
    来的 agent 的 toolset 早就已经被过滤到只剩 spec 声明过的那三个名字了,模
    型根本不知道这个工具存在。如果白名单过滤哪天没能跟上 pet-mcp 多暴露出来
    的工具,这次调用就会成功而不是报错,这个测试就会抓到。
    """
    model = TestModel(call_tools=["pet_mcp_delete_pet"])
    agent = build_agent(model, fake_pet_mcp_with_extra_tool)
    with pytest.raises(UserError, match="unknown tool 'pet_mcp_delete_pet'"):
        await agent.run("do you have any cats?")


async def test_hosted_service_accumulates_message_history(fake_pet_mcp: MCPToolset) -> None:
    """HostedAgentService is the thing that makes "remembers this conversation" true.

    HostedAgentService 就是让"记住这场对话"成立的那个东西。
    """
    service = build_hosted_service(_read_only_test_model(), fake_pet_mcp)
    async with service:
        assert service.active_sessions() == []
        first_answer = await service.handle_message("do you have any cats?", session_id="alice")
        assert isinstance(first_answer, str)
        assert service.active_sessions() == ["alice"]

        second_answer = await service.handle_message("tell me more about the first one", session_id="alice")
        assert isinstance(second_answer, str)


async def test_build_pet_mcp_toolset_wires_command_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No subprocess is actually started here - just checking what would launch it."""
    monkeypatch.setenv("PET_MCP_PROJECT_DIR", "/some/path/pet-mcp")
    monkeypatch.setenv("PETSTORE_API_BASE_URL", "http://petstore.example:9000")
    settings = Settings()

    toolset = build_pet_mcp_toolset(settings)

    transport = toolset.client.transport
    assert transport.command == "uv"
    assert transport.args == ["run", "--project", "/some/path/pet-mcp", "pet-mcp"]
    assert transport.env is not None
    assert transport.env["PETSTORE_API_BASE_URL"] == "http://petstore.example:9000"
    # The parent environment must be passed through too, or the subprocess
    # cannot even find the `uv` binary on every OS.
    # 父进程的环境变量也必须一并透传,否则子进程在某些系统上连 `uv` 这个可执行
    # 文件都找不到。
    assert "PATH" in transport.env


async def test_run_agent_raises_clear_error_when_llm_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "none")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="LLM not configured"):
            await run_agent("hello")
    finally:
        get_settings.cache_clear()
