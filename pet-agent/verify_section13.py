"""Section 13 evidence: the conversational customer-journey scenarios, against the real stack.

第 13 节证据之二:针对真实环境的、对话式的顾客旅程场景。

Sibling script to ``verify_agent_conversation.py`` (Step 6's own script,
covering the seven core agent behaviours) - this one is a superset focused on
ONBOARDING.md section 13's required scenario table, run the exact same way:
through ``pet_agent.agent.build_hosted_service`` and its
``HostedAgentService.handle_message()``, exactly as the real CLI (``cli.py``)
calls it. As with the sibling script, this file does not assert "is the
wording right" - it prints the transcript (including which pet-mcp tools were
actually called) for a human to read back against ONBOARDING.md.

Covers, in order:
    list available pets, search by species, search by price, combined
    search, search by characteristic/tag, follow-up reference, unknown pet,
    empty result, changed availability (a *direct*, out-of-band purchase
    against petstore-api - bypassing the agent entirely - simulates another
    customer buying the pet first), purchase without confirmation, cancelled
    purchase, successful purchase, repeated purchase.

跟 ``verify_agent_conversation.py``(第 6 步自己的脚本,覆盖 agent 的七种核心
行为)是姐妹脚本——这一个是它的超集,专门覆盖 ONBOARDING.md 第 13 节要求的
场景表,跑法完全一样:通过 ``pet_agent.agent.build_hosted_service`` 拿到的
``HostedAgentService.handle_message()``,跟真实 CLI(``cli.py``)调用它的方式
完全相同。跟姐妹脚本一样,这个文件不断言"说得对不对"——它只是把对话记录
(包括真正调用过哪些 pet-mcp 工具)打印出来,交给人对照 ONBOARDING.md 自己判断。

依次覆盖:列出可用宠物、按品种搜索、按价格搜索、组合搜索、按特征/标签搜索、
后续指代、未知宠物、空结果、库存变化(直接绕过 agent、对 petstore-api 发一次
带外购买,模拟"被别的顾客先买走了")、未确认就购买、取消购买、成功购买、
重复购买。

*** Heads up: this places several REAL purchases against petstore-api,
*** marking real pets "sold" (this is required to demonstrate "successful
*** purchase" and "repeated purchase" per section 13) and one real pet is
*** purchased directly (bypassing the agent) to demonstrate "changed
*** availability". Run against a store you don't mind consuming inventory
*** from - the seeded inventory, or one you have re-seeded.

*** 提醒:这个脚本会对 petstore-api 下几笔真实的购买订单,把几只真的宠物标记
*** 成"已售出"(这是第 13 节要求的"成功购买"和"重复购买"场景本身需要的),
*** 另外还会直接绕过 agent 买走一只真的宠物,用来演示"库存变化"场景。请在一
*** 个你不介意消耗库存的商店上运行——比如种子库存,或者你重新播种过的库存。

Run this from inside the pet-agent project directory (same prerequisites as
verify_agent_conversation.py - petstore-api running, pet-mcp reachable, a
real LLM configured):

    uv run python verify_section13.py

or, from the top level, against the full Dockerized stack:

    docker compose run --rm -T pet-agent uv run python verify_section13.py
"""

import asyncio
import json
import re
import sys
import urllib.error
import urllib.request

from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from pet_agent.agent import build_hosted_service, build_pet_mcp_toolset
from pet_agent.config import Settings, get_settings
from pet_agent.llm.client import create_llm

# Turns before the changed-availability interleave. Label prefix matches
# section 13's own scenario names so the transcript is easy to grep/read back.
# 库存变化那次插入操作之前的几轮对话。标签前缀跟第 13 节的场景名对上,方便
# 事后读对话记录时用它来搜。
SCRIPT_PART_1: list[tuple[str, str]] = [
    ("list available pets", "Hi, what pets do you have available right now?"),
    ("search by species", "Do you have any cats?"),
    ("search by price", "Show me pets priced under 300 euros."),
    ("combined search", "Do you have any young dogs under 500 euros?"),
    ("search by characteristic", "I'm looking for a friendly pet."),
    ("follow-up reference", "Tell me more about the second one you first showed me."),
    ("unknown pet", "Can you show me the details for pet number 999999?"),
    ("empty result", "Do you have any dragons priced under 1 euro?"),
]

# After the changed-availability interleave: the purchase-flow scenarios,
# each depending on state the previous ones just created (a fresh
# conversation turn naturally re-checks availability/price before acting).
# 库存变化插入操作之后:一串购买流程场景,每一步都依赖上一步刚造成的状
# 态(每一轮新的对话都会自然地在动作前重新核查库存/价格)。
SCRIPT_PART_2: list[tuple[str, str]] = [
    ("purchase without confirmation - prepare", "I'd like to buy a cat, please show me one."),
    ("purchase without confirmation - decline", "Actually, hold on - what other dogs do you have?"),
    ("cancelled purchase - prepare", "I'd like to buy a dog then."),
    ("cancelled purchase - cancel", "Actually, never mind, I don't want it after all."),
    ("successful purchase - prepare", "OK, show me the available cats again, I do want to buy one."),
    ("successful purchase - confirm", "Yes, please confirm the purchase of the first one."),
    ("repeated purchase", "Great, now please buy that same pet again."),
]


def _print_tool_activity(messages: list) -> None:  # type: ignore[type-arg]
    """Print which pet-mcp tools were actually called this turn, and what came back."""
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                print(f"    -> tool call: {part.tool_name}({part.args})")
            elif isinstance(part, ToolReturnPart):
                content = str(part.content)
                preview = content if len(content) <= 200 else content[:200] + "..."
                print(f"    <- tool result: {preview}")


def _extract_first_pet_id(messages: list) -> int | None:  # type: ignore[type-arg]
    """Pull a pet id out of the most recent search/get tool result, for the
    changed-availability interleave below - deliberately reads whatever pets
    the LLM actually surfaced this run, rather than assuming fixed seed data.

    从最近一次 search/get 工具结果里取一个宠物 id,给下面的库存变化插入操作
    用——这里故意读的是这次运行里模型真的展示出来的宠物,而不是假设固定不变
    的种子数据。
    """
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name in ("pet_mcp_search_pets", "pet_mcp_get_pet"):
                content = part.content
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except json.JSONDecodeError:
                        match = re.search(r'"id"\s*:\s*(\d+)', content)
                        return int(match.group(1)) if match else None
                if isinstance(content, list) and content:
                    first = content[0]
                    return int(first["id"]) if isinstance(first, dict) and "id" in first else None
                if isinstance(content, dict) and "id" in content:
                    return int(content["id"])
    return None


def _direct_purchase(settings: Settings, pet_id: int) -> tuple[int, dict]:  # type: ignore[type-arg]
    """Buy a pet directly against petstore-api, bypassing the agent entirely -
    simulates "another customer bought it first", for section 13's
    "changed availability" scenario.

    直接对 petstore-api 下单买走一只宠物,完全绕过 agent——模拟"被别的顾客
    先买走了",对应第 13 节的"库存变化"场景。
    """
    url = f"{settings.petstore_api_base_url}/pets/{pet_id}/purchase"
    # S310 is a false positive here: `url` is built from
    # settings.petstore_api_base_url (a local config value, http(s) only)
    # plus a fixed literal path - never attacker/user-controlled input.
    # S310 在这里是误报:`url` 是用 settings.petstore_api_base_url(一个本地
    # 配置值,只会是 http(s))拼上一段写死的路径构造出来的——不是攻击者/用户
    # 能控制的输入。
    req = urllib.request.Request(url, method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


async def main() -> int:
    settings = get_settings()
    if not settings.llm_enabled:
        print(
            f"error: LLM is not configured (LLM_BACKEND={settings.llm_backend!r}). "
            "See verify_agent_conversation.py's module docstring for the required variables.",
            file=sys.stderr,
        )
        return 2

    model = create_llm(settings)
    if model is None:
        print("error: create_llm() returned None despite llm_enabled=True.", file=sys.stderr)
        return 2

    toolset = build_pet_mcp_toolset(settings)
    print(f"Petstore API: {settings.petstore_api_base_url}")
    print(f"LLM backend/model: {settings.llm_backend}/{settings.llm_model}")
    print("=" * 70)

    async with build_hosted_service(model, toolset) as service:

        async def turn(label: str, user_message: str) -> list:  # type: ignore[type-arg]
            print(f"\n[{label}]")
            print(f"customer:  {user_message}")
            with capture_run_messages() as messages:
                reply = await service.handle_message(user_message, session_id="verify-section13")
            _print_tool_activity(messages)
            print(f"assistant: {reply}")
            return messages

        target_pet_id: int | None = None
        for label, user_message in SCRIPT_PART_1:
            messages = await turn(label, user_message)
            if label == "list available pets" and target_pet_id is None:
                target_pet_id = _extract_first_pet_id(messages)

        print("\n[changed availability - behind-the-scenes setup]")
        if target_pet_id is None:
            print(
                "SKIPPED: could not determine a pet id from the first turn's tool "
                "results (the assistant may not have surfaced one, e.g. if the store "
                "is empty) - nothing purchased, no follow-up turn run."
            )
        else:
            print(f"directly purchasing pet {target_pet_id} against petstore-api, bypassing the agent")
            status, body = _direct_purchase(settings, target_pet_id)
            print(f"direct purchase result: status={status} body={body}")
            await turn(
                "changed availability",
                f"I'd like to see the details for pet number {target_pet_id} and buy it if it's still available.",
            )

        for label, user_message in SCRIPT_PART_2:
            await turn(label, user_message)

    print("\n" + "=" * 70)
    print(
        "Done. Read back through the transcript above against ONBOARDING.md section 13:\n"
        "  - did every search/filter/follow-up resolve correctly to real pets?\n"
        "  - did the 'unknown pet' and 'empty result' turns give a clear, honest\n"
        "    answer instead of inventing a pet or alternatives?\n"
        "  - after the behind-the-scenes purchase, did the assistant notice the\n"
        "    pet was no longer available *before* trying to buy it again, rather\n"
        "    than blindly reporting success?\n"
        "  - did 'purchase without confirmation' and 'cancelled purchase' leave\n"
        "    those pets available (no order placed)?\n"
        "  - did 'successful purchase' place exactly one order, and did\n"
        "    'repeated purchase' immediately afterward correctly refuse (no\n"
        "    duplicate order, pet already reported sold)?\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
