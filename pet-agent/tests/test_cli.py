"""CLI dialogue tests: the loop itself, not the agent it talks to.

CLI 对话循环本身的测试,不涉及它背后真正的 agent。

``run_dialogue`` takes its ``service`` as a plain duck-typed object here
(only ``handle_message`` is ever called on it) and ``input_func``/
``print_func`` as scripted fakes, so every test runs fully offline: no real
LLM, no real pet-mcp, no real stdin/stdout.
这里给 ``run_dialogue`` 的 ``service`` 只是一个鸭子类型的对象(只会被调用
``handle_message``),``input_func``/``print_func`` 也是写好脚本的假函数,
所以每个测试都是完全离线跑的:没有真的 LLM、没有真的 pet-mcp、也没有真的
stdin/stdout。
"""

import pytest

from pet_agent.cli import WELCOME, run_dialogue


class _ScriptedInput:
    """Feeds ``input_func`` one scripted line at a time; raises EOFError once exhausted.

    每次调用给 ``input_func`` 喂一行写好的输入;用完之后抛出 EOFError。

    Mirrors what a real terminal does when the customer closes the session
    (Ctrl-D) instead of typing an exit word - ``run_dialogue`` must handle
    that the same way it handles an explicit 'exit'.
    模仿真实终端在顾客直接关掉会话(Ctrl-D)、而不是打一个退出词时的行
    为——``run_dialogue`` 必须像处理显式的 'exit' 一样处理这种情况。
    """

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def __call__(self, _prompt: str) -> str:
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)


class _FakeService:
    """Records every message handed to it and returns a canned reply.

    记录每一次收到的消息,并返回一句写死的回复。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def handle_message(self, message: str, *, session_id: str = "default") -> str:
        self.calls.append((message, session_id))
        return f"reply to: {message}"


@pytest.fixture
def fake_service() -> _FakeService:
    return _FakeService()


async def test_run_dialogue_prints_the_welcome_message(fake_service: _FakeService) -> None:
    printed: list[str] = []
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        input_func=_ScriptedInput(["exit"]),
        print_func=printed.append,
    )
    assert printed[0] == WELCOME


async def test_run_dialogue_forwards_a_message_and_prints_the_reply(fake_service: _FakeService) -> None:
    printed: list[str] = []
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        session_id="test-session",
        input_func=_ScriptedInput(["do you have any cats?", "exit"]),
        print_func=printed.append,
    )
    assert fake_service.calls == [("do you have any cats?", "test-session")]
    assert "Petstore: reply to: do you have any cats?" in printed


async def test_run_dialogue_threads_the_same_session_id_across_turns(fake_service: _FakeService) -> None:
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        session_id="alice",
        input_func=_ScriptedInput(["hi", "tell me more", "exit"]),
        print_func=lambda _line: None,
    )
    assert [session_id for _message, session_id in fake_service.calls] == ["alice", "alice"]


@pytest.mark.parametrize("exit_word", ["exit", "quit", "q", ":q", "bye", "goodbye", "EXIT", "  quit  "])
async def test_run_dialogue_recognizes_every_exit_word_case_and_whitespace_insensitively(
    fake_service: _FakeService, exit_word: str
) -> None:
    printed: list[str] = []
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        input_func=_ScriptedInput([exit_word]),
        print_func=printed.append,
    )
    assert fake_service.calls == []
    assert printed[-1] == "Petstore: Thanks for stopping by - goodbye!"


async def test_run_dialogue_skips_blank_lines_without_calling_the_service(fake_service: _FakeService) -> None:
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        input_func=_ScriptedInput(["", "   ", "hello", "exit"]),
        print_func=lambda _line: None,
    )
    assert fake_service.calls == [("hello", fake_service.calls[0][1])]


async def test_run_dialogue_ends_gracefully_on_eof_instead_of_an_exit_word(fake_service: _FakeService) -> None:
    """Customer closes the terminal (Ctrl-D) rather than typing an exit word."""
    printed: list[str] = []
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        input_func=_ScriptedInput([]),
        print_func=printed.append,
    )
    assert fake_service.calls == []
    assert printed[-1] == "\nGoodbye!"


async def test_run_dialogue_generates_a_session_id_when_none_is_given(fake_service: _FakeService) -> None:
    await run_dialogue(
        fake_service,  # type: ignore[arg-type]
        input_func=_ScriptedInput(["hello", "exit"]),
        print_func=lambda _line: None,
    )
    _message, session_id = fake_service.calls[0]
    assert session_id  # non-empty, whatever shape it takes
