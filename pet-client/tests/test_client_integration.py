"""Real end-to-end integration tests for PetstoreClient.

Unlike test_client.py (which mocks every HTTP response), this file talks to
an *actual* running petstore-api instance. It proves the whole chain really
works: PetstoreClient -> HTTP -> petstore-api -> its database -> back again -
not just that PetstoreClient reacts correctly to a hand-crafted fake response.
跟 test_client.py 不一样(那边把每个 HTTP 响应都 mock 掉了),这个文件是
真的去跟一个正在运行的 petstore-api 实例通信。它要证明的是整条链路真的
能跑通:PetstoreClient -> HTTP -> petstore-api -> 它的数据库 -> 再传回来 -
而不只是证明 PetstoreClient 对一个手写的假响应反应正确。

How to run:
运行方式:

    1. Start petstore-api (in the petstore-api project, however you normally
       do it, e.g. `docker compose up -d`), and confirm GET /health works.
       先把 petstore-api 启动起来(在 petstore-api 项目里,用你平时的方式,
       比如 `docker compose up -d`),并确认 GET /health 能正常访问。

    2. From pet-client, run:
       在 pet-client 目录下执行:

           uv run pytest tests/test_client_integration.py -v -s

       Set PETSTORE_API_BASE_URL first if petstore-api is not on the default
       http://localhost:8000, e.g. (bash):
       如果 petstore-api 不是跑在默认的 http://localhost:8000,先设置一下
       PETSTORE_API_BASE_URL 环境变量,例如(bash):

           PETSTORE_API_BASE_URL=http://localhost:8001 uv run pytest tests/test_client_integration.py -v -s

If petstore-api is not reachable, every test in this file is skipped rather
than failed - that keeps `make test`/CI green when nobody has petstore-api
running, while still giving you a real answer when they do.
如果连不上 petstore-api,这个文件里的每个测试都会被跳过(skip),而不是
判定失败——这样在没人启动 petstore-api 的情况下,`make test`/CI 也能保持
绿色,同时在真的启动了 petstore-api 的时候,又能给你一个真实的验证结果。
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest

from pet_client.client import PetstoreClient
from pet_client.exceptions import PetNotAvailableError, PetNotFoundError
from pet_client.models import Availability, PetSearch

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


@pytest.fixture
async def client() -> AsyncIterator[PetstoreClient]:
    """A real PetstoreClient pointed at BASE_URL, or a skipped test.

    一个真正指向 BASE_URL 的 PetstoreClient;连不上就直接跳过测试。
    """
    if not await _petstore_api_is_reachable():
        pytest.skip(
            f"petstore-api is not reachable at {BASE_URL} - start it first "
            "(see the module docstring for how) to run these integration tests."
        )
    async with PetstoreClient(base_url=BASE_URL) as petstore_client:
        yield petstore_client


async def test_list_pets_returns_the_seeded_inventory(client: PetstoreClient) -> None:
    """The seed data (see petstore-api/app/seed.py) should give us more than zero pets.

    种子数据(见 petstore-api/app/seed.py)应该给出不止一只宠物。
    """
    pets = await client.list_pets()
    assert len(pets) > 0


async def test_get_pet_returns_a_real_pet_from_the_database(client: PetstoreClient) -> None:
    """Look up whatever the first available pet is, and check its shape is sane.

    查一下当前第一只可购买的宠物是什么样子,检查数据的形状是合理的。

    Deliberately does not hardcode a specific pet name/id: the seed data
    could be reset or extended between runs, and this test only needs to
    prove "a real round trip through the API works", not "Luna exists".
    这里故意不写死某个具体的宠物名字/id:种子数据在不同运行之间可能被
    重置或扩充,这个测试只需要证明"一次真实的 API 往返能跑通",而不是
    证明"Luna 这只宠物存在"。
    """
    available_pets = await client.list_pets(PetSearch(availability=Availability.available))
    assert len(available_pets) > 0, "expected at least one available pet in the seed data"

    first = available_pets[0]
    fetched = await client.get_pet(pet_id=first.id)

    assert fetched.id == first.id
    assert fetched.name == first.name
    assert fetched.price_eur > 0


async def test_get_pet_raises_not_found_for_an_unknown_id(client: PetstoreClient) -> None:
    """A pet id that could not plausibly exist should raise PetNotFoundError.

    一个不可能存在的宠物 id 应该抛出 PetNotFoundError。
    """
    with pytest.raises(PetNotFoundError):
        await client.get_pet(pet_id=999_999)


async def test_purchase_pet_completes_and_then_cannot_be_repeated(client: PetstoreClient) -> None:
    """The full purchase-safety loop from the onboarding spec, run for real:

        1. Find a pet that is currently available.
        2. Purchase it - petstore-api should create an order and mark it sold.
        3. Fetching it again should show availability == sold.
        4. Purchasing the same pet a second time must raise PetNotAvailableError -
           an already-sold pet can never be purchased twice.

    入门项目规范里"购买安全"这整套流程,在这里真实地跑一遍:

        1. 找一只当前可购买的宠物。
        2. 购买它——petstore-api 应该创建一个订单,并把它标记为已售出。
        3. 再查一次这只宠物,应该看到 availability == sold。
        4. 对同一只宠物再购买一次,必须抛出 PetNotAvailableError——一只
           已经卖出的宠物不能被再次购买。
    """
    available_pets = await client.list_pets(PetSearch(availability=Availability.available))
    assert len(available_pets) > 0, "expected at least one available pet to purchase"
    pet_to_buy = available_pets[0]

    order = await client.purchase_pet(pet_id=pet_to_buy.id)
    assert order.pet_id == pet_to_buy.id
    # Per the onboarding rules, the price must come from the store, never from
    # a value the caller made up - confirm the order reflects the pet's own price.
    # 按照入门项目的规则,价格必须来自商店,而不是调用方自己编的——确认
    # 订单里的价格跟这只宠物自己的价格是一致的。
    assert order.price_eur == pet_to_buy.price_eur

    updated_pet = await client.get_pet(pet_id=pet_to_buy.id)
    assert updated_pet.availability is Availability.sold

    with pytest.raises(PetNotAvailableError):
        await client.purchase_pet(pet_id=pet_to_buy.id)
