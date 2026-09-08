"""Real end-to-end integration tests for the pet-mcp MCP tools.

Unlike test_server.py (which stubs `_petstore_client()` with a mocked
transport), this file lets the tools use their *real* `_petstore_client()`,
which talks to an actual running petstore-api over the network. It proves the
whole chain really works end to end: MCP tool -> PetstoreClient -> HTTP ->
petstore-api -> its database -> back again.
跟 test_server.py 不一样(那边把 `_petstore_client()` 换成了带 mock
transport 的假客户端),这个文件让工具用它们真正的 `_petstore_client()`,
也就是真的通过网络去跟一个正在运行的 petstore-api 通信。它要证明的是整条
链路真的能端到端跑通:MCP 工具 -> PetstoreClient -> HTTP -> petstore-api ->
它的数据库 -> 再传回来。

How to run:
运行方式:

    1. Start petstore-api (however you normally do it, e.g.
       `docker compose up -d` in the petstore-api project), and confirm
       GET /health works.
       先把 petstore-api 启动起来(用你平时的方式,比如在 petstore-api
       项目里 `docker compose up -d`),并确认 GET /health 能正常访问。

    2. From pet-mcp, run:
       在 pet-mcp 目录下执行:

           uv run pytest tests/test_server_integration.py -v -s

       Set PETSTORE_API_BASE_URL first if petstore-api is not on the default
       http://localhost:8000 - this is the exact same environment variable
       `_petstore_client()` in server.py reads, e.g. (bash):
       如果 petstore-api 不是跑在默认的 http://localhost:8000,先设置一下
       PETSTORE_API_BASE_URL 环境变量——这跟 server.py 里 `_petstore_client()`
       读取的是同一个环境变量,例如(bash):

           PETSTORE_API_BASE_URL=http://localhost:8001 uv run pytest tests/test_server_integration.py -v -s

If petstore-api is not reachable, every test in this file is skipped rather
than failed - that keeps `make test`/CI green when nobody has petstore-api
running, while still giving you a real answer when they do.
如果连不上 petstore-api,这个文件里的每个测试都会被跳过(skip),而不是
判定失败——这样在没人启动 petstore-api 的情况下,`make test`/CI 也能保持
绿色,同时在真的启动了 petstore-api 的时候,又能给你一个真实的验证结果。
"""

import os

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pet_client import Availability

from pet_mcp import server

BASE_URL = os.environ.get("PETSTORE_API_BASE_URL", "http://localhost:8000")


async def _petstore_api_is_reachable() -> bool:
    """Ping GET /health with a short timeout to decide whether to skip.

    用一个很短的超时去 ping GET /health,来判断要不要跳过这些测试。
    """
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=1.5) as probe:
            response = await probe.get("/health")
            return response.status_code == 200
    except httpx.RequestError:
        return False


@pytest.fixture(autouse=True)
async def _skip_unless_petstore_api_is_up() -> None:
    """Skip every test in this file when petstore-api cannot be reached.

    连不上 petstore-api 时,跳过这个文件里的每一个测试。
    """
    if not await _petstore_api_is_reachable():
        pytest.skip(
            f"petstore-api is not reachable at {BASE_URL} - start it first "
            "(see the module docstring for how) to run these integration tests."
        )


async def test_search_pets_returns_the_seeded_inventory() -> None:
    """The seed data (see petstore-api/app/seed.py) should give us more than zero pets.

    种子数据(见 petstore-api/app/seed.py)应该给出不止一只宠物。
    """
    pets = await server.pet_mcp_search_pets()
    assert len(pets) > 0
    # Structured, dict output - exactly what an MCP client would receive.
    # 结构化的 dict 输出——跟 MCP 客户端实际会收到的东西完全一样。
    assert all(isinstance(pet, dict) and "id" in pet and "price_eur" in pet for pet in pets)


async def test_get_pet_returns_a_real_pet_and_rejects_an_unknown_id() -> None:
    """Look up whatever the first available pet is, then a pet id that cannot exist.

    先查一下当前第一只可购买的宠物,再查一个不可能存在的宠物 id。

    Deliberately does not hardcode a specific pet name/id: the seed data
    could be reset or extended between runs, and this test only needs to
    prove "a real round trip through the MCP tool and the API works".
    这里故意不写死某个具体的宠物名字/id:种子数据在不同运行之间可能被
    重置或扩充,这个测试只需要证明"一次真实的、经过 MCP 工具和 API 的
    往返能跑通"。
    """
    available_pets = await server.pet_mcp_search_pets(availability=Availability.available)
    assert len(available_pets) > 0, "expected at least one available pet in the seed data"

    first = available_pets[0]
    fetched = await server.pet_mcp_get_pet(pet_id=first["id"])
    assert fetched["id"] == first["id"]
    assert fetched["name"] == first["name"]

    with pytest.raises(ToolError, match="PET_NOT_FOUND"):
        await server.pet_mcp_get_pet(pet_id=999_999)


async def test_purchase_without_confirm_is_rejected_before_any_purchase_happens() -> None:
    """confirm=False must be rejected, and must not touch the store at all.

    confirm=False 必须被拒绝,而且完全不能碰到商店。

    Picks a real available pet first so that, if the confirmation gate were
    ever accidentally removed, this test would actually purchase it and the
    next test's assumptions would break loudly - instead of the gate's
    absence going unnoticed.
    这里先挑一只真实存在、当前可购买的宠物,这样万一确认关卡不小心被
    去掉了,这个测试就会真的把它买掉,下一个测试的前提条件会明显地被
    打破——而不是让"关卡消失了"这件事悄无声息地被漏过去。
    """
    available_pets = await server.pet_mcp_search_pets(availability=Availability.available)
    assert len(available_pets) > 0, "expected at least one available pet to attempt this against"

    with pytest.raises(ToolError, match="CONFIRMATION_REQUIRED"):
        await server.pet_mcp_purchase_pet(pet_id=available_pets[0]["id"], confirm=False)

    # Still available - the rejected attempt above must have been a no-op.
    # 仍然可购买——上面被拒绝的那次尝试必须是完全没有产生任何效果的。
    still_available = await server.pet_mcp_get_pet(pet_id=available_pets[0]["id"])
    assert still_available["availability"] == Availability.available.value


async def test_purchase_pet_completes_and_then_cannot_be_repeated() -> None:
    """The full purchase-safety loop from the onboarding spec, run for real:

        1. Find a pet that is currently available.
        2. Confirm its live price and availability via pet_mcp_get_pet.
        3. Purchase it with confirm=True - petstore-api creates an order and
           marks it sold.
        4. Fetching it again shows availability == sold.
        5. Purchasing the same pet a second time must raise a
           PET_NOT_AVAILABLE ToolError.

    入门项目规范里"购买安全"这整套流程,在这里真实地跑一遍:

        1. 找一只当前可购买的宠物。
        2. 通过 pet_mcp_get_pet 确认它当前的价格和可购买状态。
        3. 用 confirm=True 购买它——petstore-api 创建一个订单,并把它标记
           为已售出。
        4. 再查一次这只宠物,应该看到 availability == sold。
        5. 对同一只宠物再购买一次,必须抛出 PET_NOT_AVAILABLE 的 ToolError。
    """
    available_pets = await server.pet_mcp_search_pets(availability=Availability.available)
    assert len(available_pets) > 0, "expected at least one available pet to purchase"
    pet_to_buy = available_pets[0]

    shown_to_customer = await server.pet_mcp_get_pet(pet_id=pet_to_buy["id"])
    assert shown_to_customer["availability"] == Availability.available.value

    order = await server.pet_mcp_purchase_pet(pet_id=pet_to_buy["id"], confirm=True)
    assert order["pet_id"] == pet_to_buy["id"]
    # Per the onboarding rules, the price must come from the store, never from
    # a value the caller made up - confirm the order reflects the pet's own price.
    # 按照入门项目的规则,价格必须来自商店,而不是调用方自己编的——确认
    # 订单里的价格跟这只宠物自己的价格是一致的。
    assert order["price_eur"] == shown_to_customer["price_eur"]

    updated_pet = await server.pet_mcp_get_pet(pet_id=pet_to_buy["id"])
    assert updated_pet["availability"] == Availability.sold.value

    with pytest.raises(ToolError, match="PET_NOT_AVAILABLE"):
        await server.pet_mcp_purchase_pet(pet_id=pet_to_buy["id"], confirm=True)
