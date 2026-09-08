"""Tests for PetstoreClient's HTTP-to-exception translation.

These tests do not talk to a real petstore-api instance. Instead, we swap
httpx's transport for `httpx.MockTransport`, a built-in httpx test helper
that lets us return a canned response (or raise a connection error) for a
given request without any network I/O. This keeps the tests fast and
deterministic, and is exactly the "verify the MCP/client layer works
without needing an LLM" requirement from the onboarding spec.
测试 PetstoreClient 把 HTTP 结果翻译成异常这部分逻辑。

这些测试不会真的去跟一个跑起来的 petstore-api 实例通信。而是把 httpx 的
transport 换成 `httpx.MockTransport`——这是 httpx 内置的一个测试工具,
可以让我们针对一个给定的请求返回一个预设的响应(或者抛出一个连接错误),
完全不需要真实的网络 I/O。这样测试跑得快、结果也是确定的,而且正好对应
入门项目文档里"不需要 LLM 也能验证 MCP/客户端这一层能正常工作"这条要求。

A separate, real integration test (against a running petstore-api, e.g. via
docker compose) should be added alongside these to prove the mapping still
matches production behaviour — this file only proves PetstoreClient itself
behaves correctly given a known HTTP response.
以后应该再补一套单独的、真实的集成测试(针对一个真正跑起来的
petstore-api,比如通过 docker compose 拉起来),用来证明这套映射关系跟
生产环境的真实行为还是一致的——这个文件只证明了 PetstoreClient 本身在
拿到一个已知的 HTTP 响应时,行为是正确的。
"""

import httpx
import pytest

from pet_client.client import PetstoreClient
from pet_client.exceptions import (
    InvalidRequestError,
    PetNotAvailableError,
    PetNotFoundError,
    StoreUnavailableError,
)
from pet_client.models import Availability, Pet, PetSearch, Species

SAMPLE_PET = {
    "id": 1,
    "name": "Luna",
    "species": "cat",
    "specific_species": None,
    "breed": "Domestic Shorthair",
    "age_months": 24,
    "weight_kg": 4.1,
    "tail_length_cm": 27.0,
    "description": "A gentle and friendly cat.",
    "price_eur": 250.0,
    "availability": "available",
    "tags": ["gentle", "friendly"],
    "photo_references": ["luna.jpg"],
}


def make_client(handler: httpx.MockTransport) -> PetstoreClient:
    """Build a PetstoreClient wired to a fake transport instead of the network.

    The transport must be passed in at construction time (via PetstoreClient's
    `transport` parameter) rather than assigned afterwards - httpx.AsyncClient
    also keeps a separate `_mounts` table for proxy configuration that takes
    priority over a transport swapped in post-construction, so a naive
    `client._http._transport = handler` assignment would silently still send
    requests out over the real network.

    构造一个接到假 transport(而不是真实网络)上的 PetstoreClient。

    这个 transport 必须在构造的时候就传进去(通过 PetstoreClient 的
    `transport` 参数),而不是构造完之后再赋值——httpx.AsyncClient 还有
    一张单独的 `_mounts` 表用于代理配置,它的优先级比构造完之后再换上去
    的 transport 更高,所以如果天真地写
    `client._http._transport = handler`,请求还是会悄悄地真的发到网络上。
    """
    return PetstoreClient(base_url="http://petstore-api.test", transport=handler)


async def test_list_pets_parses_a_successful_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets"
        return httpx.Response(200, json=[SAMPLE_PET])

    client = make_client(httpx.MockTransport(handler))
    async with client:
        pets = await client.list_pets(PetSearch(species=Species.cat))

    assert pets == [Pet.model_validate(SAMPLE_PET)]


async def test_list_pets_sends_only_the_filters_that_were_set() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.url.params)
        return httpx.Response(200, json=[])

    client = make_client(httpx.MockTransport(handler))
    async with client:
        await client.list_pets(PetSearch(species=Species.cat, max_price_eur=300))

    # name_contains, breed, etc. were never set, so exclude_none must have
    # dropped them rather than sending them as the literal string "None".
    # name_contains、breed 等字段从来没被设置过,所以 exclude_none 必须把
    # 它们丢掉,而不是把它们当作字面字符串 "None" 发出去。
    assert captured == {"species": "cat", "max_price_eur": "300.0"}


async def test_get_pet_returns_a_typed_pet() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets/1"
        return httpx.Response(200, json=SAMPLE_PET)

    client = make_client(httpx.MockTransport(handler))
    async with client:
        pet = await client.get_pet(pet_id=1)

    assert pet.name == "Luna"
    assert pet.availability is Availability.available


async def test_get_pet_raises_pet_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Pet 999 not found"})

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(PetNotFoundError) as exc_info:
            await client.get_pet(pet_id=999)

    assert exc_info.value.pet_id == 999


async def test_purchase_pet_returns_a_typed_order_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets/1/purchase"
        assert request.method == "POST"
        return httpx.Response(201, json={"id": 1048, "pet_id": 1, "price_eur": 250.0})

    client = make_client(httpx.MockTransport(handler))
    async with client:
        order = await client.purchase_pet(pet_id=1)

    assert order.id == 1048
    assert order.price_eur == 250.0


async def test_purchase_pet_raises_pet_not_available_on_409() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Pet 1 is not available"})

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(PetNotAvailableError) as exc_info:
            await client.purchase_pet(pet_id=1)

    assert exc_info.value.pet_id == 1


async def test_purchase_pet_raises_pet_not_found_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Pet 999 not found"})

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(PetNotFoundError):
            await client.purchase_pet(pet_id=999)


async def test_invalid_search_raises_invalid_request_error_on_422() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="min_price_eur cannot exceed max_price_eur")

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(InvalidRequestError):
            await client.list_pets(PetSearch(min_price_eur=500, max_price_eur=100))


async def test_server_error_raises_store_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error")

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(StoreUnavailableError):
            await client.get_pet(pet_id=1)


async def test_connection_failure_raises_store_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = make_client(httpx.MockTransport(handler))
    async with client:
        with pytest.raises(StoreUnavailableError):
            await client.get_pet(pet_id=1)
