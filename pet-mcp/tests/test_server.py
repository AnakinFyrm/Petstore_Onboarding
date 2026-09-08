"""Tests for the MCP tools.

The tools are exercised directly (they are plain functions) and once through the
server's registry, so a tool that is written but never registered is caught.
Every tool talks to Petstore through `pet_mcp.server._petstore_client()`, so
tests monkeypatch that one function to return a PetstoreClient wired to
`httpx.MockTransport` instead of the real network - the same pattern used in
pet_client's own test suite.
测试这几个 MCP 工具。

工具本身是普通函数,直接调用来测试;同时也通过 server 的工具注册表测一遍,
这样"写了但忘了注册"的工具能被发现。每个工具都是通过
`pet_mcp.server._petstore_client()` 跟 Petstore 打交道的,所以测试只需要
monkeypatch 这一个函数,让它返回一个接了 `httpx.MockTransport`(而不是真实
网络)的 PetstoreClient——跟 pet_client 自己测试套件里用的是同一套手法。
"""

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pet_client import PetstoreClient, Species

from pet_mcp import server

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


def _stub_petstore_client(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    """Make every tool's `_petstore_client()` call return a client wired to `handler`.

    让每个工具里调用的 `_petstore_client()`,都返回一个接到 `handler` 上的
    客户端。
    """
    monkeypatch.setattr(
        server,
        "_petstore_client",
        lambda: PetstoreClient(base_url="http://petstore-api.test", transport=handler),
    )


async def test_tools_are_registered() -> None:
    names = {tool.name for tool in await server.mcp.list_tools()}
    assert {"pet_mcp_search_pets", "pet_mcp_get_pet", "pet_mcp_purchase_pet"} <= names


async def test_search_pets_returns_store_results(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets"
        return httpx.Response(200, json=[SAMPLE_PET])

    _stub_petstore_client(monkeypatch, httpx.MockTransport(handler))

    results = await server.pet_mcp_search_pets(species=Species.cat)

    assert results == [SAMPLE_PET]


async def test_get_pet_returns_the_pet(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets/1"
        return httpx.Response(200, json=SAMPLE_PET)

    _stub_petstore_client(monkeypatch, httpx.MockTransport(handler))

    result = await server.pet_mcp_get_pet(pet_id=1)

    assert result["name"] == "Luna"


async def test_get_pet_raises_tool_error_when_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Pet 999 not found"})

    _stub_petstore_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ToolError, match="PET_NOT_FOUND"):
        await server.pet_mcp_get_pet(pet_id=999)


async def test_purchase_pet_without_confirm_is_rejected_before_any_network_call() -> None:
    # No monkeypatch here on purpose: if the confirmation gate were missing,
    # this would try a real network call and fail loudly rather than silently
    # "succeeding" for the wrong reason.
    # 这里故意不做 monkeypatch:如果确认关卡没生效,这个调用会尝试一次真实
    # 的网络请求并且明显地失败,而不会因为错误的原因"悄悄地成功"。
    with pytest.raises(ToolError, match="CONFIRMATION_REQUIRED"):
        await server.pet_mcp_purchase_pet(pet_id=1, confirm=False)


async def test_purchase_pet_with_confirm_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/pets/1/purchase"
        assert request.method == "POST"
        return httpx.Response(201, json={"id": 1048, "pet_id": 1, "price_eur": 250.0})

    _stub_petstore_client(monkeypatch, httpx.MockTransport(handler))

    result = await server.pet_mcp_purchase_pet(pet_id=1, confirm=True)

    assert result == {"id": 1048, "pet_id": 1, "price_eur": 250.0}


async def test_purchase_pet_raises_tool_error_when_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Pet 1 is not available"})

    _stub_petstore_client(monkeypatch, httpx.MockTransport(handler))

    with pytest.raises(ToolError, match="PET_NOT_AVAILABLE"):
        await server.pet_mcp_purchase_pet(pet_id=1, confirm=True)
