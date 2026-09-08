"""Manual, real-service run through Step 6's seven behaviours.

真实接上 petstore-api + pet-mcp + OpenRouter,把第 6 步(ONBOARDING.md 第 12
节)要求的那七种行为过一遍。这个脚本自己不断言"对不对"——需要你读一遍打印
出来的对话记录,照着 ONBOARDING.md 第 9/10 节自己判断 Agent 的回答合不合规矩。

自第 7 步起,这个脚本不再自己创建 PetstoreAgentSession,而是通过
pet_agent.agent.build_hosted_service 得到一个 pet_aes.HostedAgentService,再
调用它的 handle_message() —— 这跟未来 CLI/AES 托管服务实际调用这个 agent 的
方式完全一样。

跑之前请确认:
    1. petstore-api 已经在跑,而且这里的 PETSTORE_API_BASE_URL 指向它。
    2. pet-mcp 项目就在 PET_MCP_PROJECT_DIR 指的路径上,并且它自己的
       环境变量里配的是同一个 PETSTORE_API_BASE_URL。
    3. pet-agent 自己配好了真实可用的 LLM:
       LLM_BACKEND=openai_compat
       OPENAI_BASE_URL=https://openrouter.ai/api/v1
       OPENAI_API_KEY=<你的 OpenRouter 密钥>
       LLM_MODEL=z-ai/glm-5.3-flash (或者你在第 5 步验证过的其他模型)
    这些通常放在 .env.dev 或者进程环境变量里,不要提交到 git。

*** 注意:第 5、6 句会真的对 petstore-api 下一笔购买订单,把一只宠物标记
*** 成"已售出"。如果不想动库存,把 SCRIPT 里第 5、6 行的话换成"算了,不买了"
*** 之类的取消说法,顺便验证一下第 9 节"顾客取消购买"的场景。

在 pet-agent 项目目录下运行:
    uv run python verify_agent_conversation.py

---

Before running, make sure:
    1. petstore-api is already running, with PETSTORE_API_BASE_URL below
       pointing at it.
    2. pet-mcp exists at PET_MCP_PROJECT_DIR, configured with that same
       PETSTORE_API_BASE_URL.
    3. pet-agent itself has a real, working LLM configured:
       LLM_BACKEND=openai_compat
       OPENAI_BASE_URL=https://openrouter.ai/api/v1
       OPENAI_API_KEY=<your OpenRouter key>
       LLM_MODEL=z-ai/glm-5.3-flash (or whatever you verified in Step 5)
    These normally live in .env.dev or the process environment - never commit
    real secrets.

As of Step 7, this script no longer creates a PetstoreAgentSession itself -
it gets a pet_aes.HostedAgentService from pet_agent.agent.build_hosted_service
and calls its handle_message() instead, exactly the way a future CLI/AES-
hosted service will actually call this agent.

*** Heads up: turns 5 and 6 will place a REAL purchase against petstore-api,
*** marking one real pet "sold". If you would rather not touch inventory,
*** replace those two lines in SCRIPT with a change-of-mind line instead
*** ("actually, never mind") to exercise section 9's cancellation path.

Run this from inside the pet-agent project directory:
    uv run python verify_agent_conversation.py
"""

import asyncio
import sys

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from pet_agent.agent import build_hosted_service, build_pet_mcp_toolset
from pet_agent.config import get_settings
from pet_agent.llm.client import create_llm

# Each line is one customer turn. The labels are the seven behaviours listed
# in ONBOARDING.md section 12, step 6 - "roughly" in order, because a real
# model may fold two behaviours into one reply, which is fine and expected.
# 每一行是顾客说的一句话。标签对应 ONBOARDING.md 第 12 节第 6 步列的那七种
# 行为——"大致"按顺序,因为真的模型完全可能把两种行为揉进一句回复里,这是
# 正常、预期之内的。
SCRIPT: list[tuple[str, str]] = [
    ("1. list pets", "Hi, what pets do you have available right now?"),
    ("2. filter pets", "Do you have any dogs?"),
    ("3. pet details", "Tell me more about the first one you showed me."),
    ("4. follow-up reference", "How much is it, and is it still available?"),
    ("5. prepare a purchase", "I'd like to buy it."),
    ("6. confirm and purchase", "Yes, confirm the purchase."),
    ("7. explain a failure", "Can I also buy a dragon?"),
]


def _print_tool_activity(messages: list) -> None:  # type: ignore[type-arg]
    """Print which pet-mcp tools were actually called this turn, and what came back.

    打印这一轮里真正被调用的 pet-mcp 工具,以及返回了什么。
    """
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                print(f"    -> tool call: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                content = str(part.content)
                preview = content if len(content) <= 200 else content[:200] + "..."
                print(f"    <- tool result: {preview}")


async def main() -> int:
    settings = get_settings()
    if not settings.llm_enabled:
        print(
            f"error: LLM is not configured (LLM_BACKEND={settings.llm_backend!r}). "
            "Set LLM_BACKEND=openai_compat, OPENAI_BASE_URL, OPENAI_API_KEY and "
            "LLM_MODEL first - see the module docstring above.",
            file=sys.stderr,
        )
        return 2

    model = create_llm(settings)
    if model is None:
        print(
            "error: create_llm() returned None despite llm_enabled=True - "
            "check the warning logged just above this line.",
            file=sys.stderr,
        )
        return 2

    toolset = build_pet_mcp_toolset(settings)
    print(f"Launching pet-mcp via: uv run --project {settings.pet_mcp_project_dir} pet-mcp")
    print(f"Petstore API: {settings.petstore_api_base_url}")
    print(f"LLM backend/model: {settings.llm_backend}/{settings.llm_model}")
    print("=" * 70)

    async with build_hosted_service(model, toolset) as service:
        for label, user_message in SCRIPT:
            print(f"\n[{label}]")
            print(f"customer:  {user_message}")
            with capture_run_messages() as messages:
                reply = await service.handle_message(user_message, session_id="verify-script")
            _print_tool_activity(messages)
            print(f"assistant: {reply}")

    print("\n" + "=" * 70)
    print(
        "Done. Read back through the transcript above against ONBOARDING.md\n"
        "section 9/10: did the assistant re-check price/availability\n"
        "immediately before the purchase call, ask for explicit confirmation\n"
        "before buying, avoid inventing an order number or receipt for the\n"
        "failure case, and correctly resolve 'it' / 'the first one' to the\n"
        "pet actually shown earlier in the conversation?\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
