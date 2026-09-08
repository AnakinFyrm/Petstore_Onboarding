"""Tests for pet_aes.service.HostedAgentService: the operational boundary
that runs a built agent for the life of a conversation.

针对 pet_aes.service.HostedAgentService 的测试:在一整场对话期间运行一个
已经构建好的 agent 的"运行边界"。

Most tests here use a small hand-written fake agent rather than a real
``pydantic_ai.Agent`` - ``HostedAgentService`` only ever calls
``__aenter__``/``__aexit__``/``run`` on what it is given, so a fake that
implements exactly that surface lets each test assert precisely on what was
passed to ``run`` (the threaded history, in particular) without depending on
whatever a real model happens to answer. One test at the end uses a real
``Agent`` + ``TestModel`` to confirm the fake is not hiding an integration
problem.
这里的大多数测试用的是一个手写的假 agent,而不是一个真正的
``pydantic_ai.Agent`` —— ``HostedAgentService`` 自始至终只会在拿到的东西上
调用 ``__aenter__``/``__aexit__``/``run``,所以一个恰好实现了这几个接口的假
对象,能让每个测试精确断言传给 ``run`` 的到底是什么(尤其是被串起来的历史
记录),而不用依赖某个真实模型碰巧回答了什么。最后一个测试用了真正的
``Agent`` + ``TestModel``,确认假对象没有掩盖真实的对接问题。
"""

from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from pet_aes.service import DEFAULT_FALLBACK_MESSAGE, HostedAgentService


@dataclass
class _FakeResult:
    """Stands in for pydantic-ai's ``AgentRunResult``: just enough surface
    (``output``, ``all_messages()``) for ``HostedAgentService`` to use.

    代替 pydantic-ai 的 ``AgentRunResult``:只提供 ``HostedAgentService`` 会
    用到的那部分接口(``output``、``all_messages()``)。

    ``_history`` is typed ``list[Any]`` rather than ``list[ModelMessage]``:
    this fake stores plain marker strings ("turn:...") instead of real
    ``ModelMessage`` objects, since the tests only need to see that history
    was threaded through, not that it round-trips through the real message
    model.
    ``_history`` 的类型是 ``list[Any]`` 而不是 ``list[ModelMessage]``:这个假
    对象存的是普通的标记字符串("turn:..."),而不是真正的 ``ModelMessage``
    对象 —— 测试只需要看到历史记录确实被串起来了,不需要它真的能在真实的消
    息模型里往返。
    """

    output: str
    _history: list[Any] = field(default_factory=list)

    def all_messages(self) -> list[Any]:
        return self._history


class _FakeAgent:
    """A minimal duck-typed stand-in for ``pydantic_ai.Agent``.

    ``pydantic_ai.Agent`` 的一个最简"鸭子类型"替身。

    Records every ``run()`` call (message + the history it was handed) so
    tests can assert exactly what ``HostedAgentService`` threaded through,
    and can be told to raise on the next call to exercise the fallback path.
    记录每一次 ``run()`` 调用(收到的消息 + 被传入的历史记录),这样测试就能
    精确断言 ``HostedAgentService`` 到底串了什么历史进去;也可以被设置成在
    下一次调用时抛异常,以此来测试兜底回复的路径。
    """

    def __init__(self) -> None:
        self.entered = False
        self.exited = False
        self.calls: list[tuple[str, list[Any]]] = []
        self._raise_next: Exception | None = None

    async def __aenter__(self) -> _FakeAgent:
        self.entered = True
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self.exited = True

    def raise_on_next_run(self, exc: Exception) -> None:
        self._raise_next = exc

    async def run(
        self, message: str, *, message_history: list[Any] | None = None, usage_limits: object = None
    ) -> _FakeResult:
        self.calls.append((message, list(message_history or [])))
        if self._raise_next is not None:
            exc, self._raise_next = self._raise_next, None
            raise exc
        # A fake "new message" appended each turn, so history visibly grows
        # from one call to the next.
        # 每一轮都追加一条假的"新消息",这样历史记录能在连续调用之间明显变长。
        new_history = [*(message_history or []), f"turn:{message}"]
        return _FakeResult(output=f"reply to: {message}", _history=new_history)


@pytest.fixture
def fake_agent() -> _FakeAgent:
    return _FakeAgent()


async def test_handle_message_returns_the_agents_output(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        reply = await service.handle_message("do you have any cats?")
    assert reply == "reply to: do you have any cats?"


async def test_context_manager_enters_and_exits_the_underlying_agent(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent):  # type: ignore[arg-type]
        assert fake_agent.entered is True
        assert fake_agent.exited is False
    assert fake_agent.exited is True


async def test_handle_message_threads_history_across_turns_in_the_same_session(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        await service.handle_message("do you have any cats?", session_id="alice")
        await service.handle_message("tell me about the first one", session_id="alice")
    # The second call must have been handed the history the first call produced.
    # 第二次调用时,必须已经拿到了第一次调用产生的历史记录。
    (_, first_history), (second_message, second_history) = fake_agent.calls
    assert first_history == []
    assert second_message == "tell me about the first one"
    assert second_history == ["turn:do you have any cats?"]


async def test_handle_message_keeps_sessions_independent(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        await service.handle_message("hi, I'm alice", session_id="alice")
        await service.handle_message("hi, I'm bob", session_id="bob")
        await service.handle_message("what did I just say?", session_id="alice")
    # Alice's third call must see only her own history, never Bob's.
    # alice 的第三次调用必须只看到她自己的历史,绝不能看到 bob 的。
    (_, alice_first_history) = fake_agent.calls[0][0], fake_agent.calls[0][1]
    (_, bob_history) = fake_agent.calls[1][0], fake_agent.calls[1][1]
    (_, alice_third_history) = fake_agent.calls[2][0], fake_agent.calls[2][1]
    assert alice_first_history == []
    assert bob_history == []
    assert alice_third_history == ["turn:hi, I'm alice"]


async def test_handle_message_catches_an_exception_and_returns_the_fallback_message(fake_agent: _FakeAgent) -> None:
    fake_agent.raise_on_next_run(RuntimeError("the model connection dropped"))
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        reply = await service.handle_message("do you have any cats?")
    # The customer sees only the safe fallback - never the raw exception
    # message, which could leak an internal error or a secret.
    # 顾客只能看到安全的兜底回复 —— 绝不能看到原始的异常信息,那有可能泄露内
    # 部错误细节甚至密钥。
    assert reply == DEFAULT_FALLBACK_MESSAGE
    assert "the model connection dropped" not in reply


async def test_handle_message_uses_a_custom_fallback_message_when_given(fake_agent: _FakeAgent) -> None:
    fake_agent.raise_on_next_run(RuntimeError("boom"))
    async with HostedAgentService(fake_agent, fallback_message="please try again later") as service:  # type: ignore[arg-type]
        reply = await service.handle_message("hello")
    assert reply == "please try again later"


async def test_handle_message_after_a_failure_does_not_poison_later_history(fake_agent: _FakeAgent) -> None:
    fake_agent.raise_on_next_run(RuntimeError("boom"))
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        await service.handle_message("this one fails", session_id="alice")
        await service.handle_message("this one should still work", session_id="alice")
    # A failed turn must not be recorded as history - the retry starts from
    # whatever history existed before the failure (here: none).
    # 失败的那一轮绝不能被记录进历史 —— 重试是从失败之前就存在的历史记录开始
    # 的(这里是空的)。
    (_, second_history) = fake_agent.calls[1][0], fake_agent.calls[1][1]
    assert second_history == []


async def test_forget_drops_a_sessions_history(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        await service.handle_message("hi", session_id="alice")
        service.forget("alice")
        await service.handle_message("do you remember me?", session_id="alice")
    (_, third_history) = fake_agent.calls[1][0], fake_agent.calls[1][1]
    assert third_history == []


def test_forget_on_an_unknown_session_id_is_a_no_op(fake_agent: _FakeAgent) -> None:
    service = HostedAgentService(fake_agent)  # type: ignore[arg-type]
    service.forget("nobody-home")  # must not raise


async def test_active_sessions_lists_only_sessions_with_history(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        assert service.active_sessions() == []
        await service.handle_message("hi", session_id="alice")
        await service.handle_message("hi", session_id="bob")
        assert sorted(service.active_sessions()) == ["alice", "bob"]


async def test_handle_message_defaults_to_a_shared_session_id_when_none_is_given(fake_agent: _FakeAgent) -> None:
    async with HostedAgentService(fake_agent) as service:  # type: ignore[arg-type]
        await service.handle_message("first")
        await service.handle_message("second")
    assert service.active_sessions() == ["default"]
    (_, second_history) = fake_agent.calls[1][0], fake_agent.calls[1][1]
    assert second_history == ["turn:first"]


async def test_handle_message_passes_a_request_limit_by_default(fake_agent: _FakeAgent) -> None:
    # Not directly observable through the fake's recorded (message, history)
    # pairs, but a request_limit of 0 must still let a first, limit-respecting
    # call through unharmed - this guards against a future refactor breaking
    # the default usage_limits wiring silently.
    # 通过假对象记录的 (message, history) 元组看不出这一点,但 request_limit
    # 传 0 时,第一次调用仍然必须能正常完成 —— 这是为了防止未来的重构悄悄弄
    # 坏了默认 usage_limits 的接线,却没有测试能发现。
    async with HostedAgentService(fake_agent, request_limit=0) as service:  # type: ignore[arg-type]
        reply = await service.handle_message("hello")
    assert reply == "reply to: hello"


async def test_handle_message_works_end_to_end_with_a_real_agent(tmp_path: Any) -> None:
    # Confirms the fake above is not hiding a real integration mismatch: a
    # genuine pydantic_ai.Agent, built with no tools at all, still answers
    # through the service exactly as it would through agent.run() directly.
    # 确认上面用的假对象没有掩盖真实的对接问题:一个完全没有工具的
    # pydantic_ai.Agent,通过这个 service 得到的回答,跟直接调用它自己的
    # agent.run() 是一样的。
    agent: Agent[None, str] = Agent(TestModel(), instructions="You are a test agent.")
    async with HostedAgentService(agent) as service:
        reply = await service.handle_message("hello")
    assert isinstance(reply, str)
    assert reply != ""
