"""HTTP client for the Petstore API.

This is the single place in the whole system (outside of petstore-api
itself) that is allowed to know petstore-api's URL, its HTTP verbs, and its
status codes. Everything above this layer (MCP server tools, eventually the
agent) should only ever see `PetstoreClient`'s three methods and the
exceptions in exceptions.py.
这是整个系统里(除了 petstore-api 自己以外)唯一一个被允许知道
petstore-api 的 URL、HTTP 方法和状态码的地方。这一层之上的所有组件
(MCP 服务器的工具、以后的 agent)都应该只看到 `PetstoreClient` 的三个
方法和 exceptions.py 里的异常。

Async, not sync: the MCP server (and, later, the AES-hosted agent) run
async code, so this client uses `httpx.AsyncClient` throughout rather than
mixing sync HTTP calls into an async call stack, which would block the
event loop.
用异步而不是同步:MCP 服务器(以及以后 AES 托管的 agent)跑的都是异步
代码,所以这个客户端全程用 `httpx.AsyncClient`,而不是在异步调用栈里
混用同步 HTTP 调用——那样会阻塞事件循环。

Status code mapping below was cross-checked against the actual exception
handling in petstore-api/app/main.py (not guessed):
    - GET  /pets/{pet_id}            -> 404 on crud.PetNotFoundError
    - POST /pets/{pet_id}/purchase   -> 404 on crud.PetNotFoundError
                                      -> 409 on crud.PetNotAvailableError
    - GET  /pets (search)            -> 422 on invalid PetSearch construction
                                         (also FastAPI's own query validation,
                                         e.g. min_age_months < 0, uses 422)
    - anything else 5xx, or a connection failure -> StoreUnavailableError
下面的状态码映射是跟 petstore-api/app/main.py 里实际的异常处理逻辑核对过的
(不是猜的):
    - GET  /pets/{pet_id}            -> crud.PetNotFoundError 对应 404
    - POST /pets/{pet_id}/purchase   -> crud.PetNotFoundError 对应 404
                                      -> crud.PetNotAvailableError 对应 409
    - GET  /pets(搜索)               -> PetSearch 构造失败对应 422
                                         (FastAPI 自己的查询参数校验,比如
                                         min_age_months < 0,也是用 422)
    - 其他任何 5xx,或者连接失败 -> StoreUnavailableError
"""

from types import TracebackType
from typing import Any

import httpx

from pet_client.exceptions import (
    InvalidRequestError,
    PetNotAvailableError,
    PetNotFoundError,
    PurchaseFailedError,
    StoreUnavailableError,
)
from pet_client.models import Order, Pet, PetSearch


class PetstoreClient:
    """Thin async wrapper around the petstore-api HTTP endpoints.

    围绕 petstore-api 的 HTTP 接口做的一层薄薄的异步封装。

    Usage:
        async with PetstoreClient(base_url="http://petstore-api:8000") as client:
            pets = await client.list_pets(PetSearch(species=Species.cat))
            pet = await client.get_pet(pet_id=1)
            order = await client.purchase_pet(pet_id=1)

    `base_url` is passed in by the caller (e.g. read from an environment
    variable such as PETSTORE_API_BASE_URL by whichever project embeds this
    client) rather than being hardcoded or read from the environment here —
    this class should stay agnostic of *where* its configuration comes from.

    `base_url` 是由调用方传进来的(比如由引用这个客户端的项目自己从
    PETSTORE_API_BASE_URL 这样的环境变量里读取),而不是在这里写死或者
    直接读环境变量——这个类应该对"配置到底从哪来"这件事保持无感知。
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # A single shared AsyncClient reuses connections (keep-alive) across
        # calls instead of opening a new TCP/TLS connection every request.
        # 用一个共享的 AsyncClient,让多次调用之间复用连接(keep-alive),
        # 而不是每次请求都重新建立一次 TCP/TLS 连接。
        #
        # `transport` is a test seam, not something production callers need:
        # passing it lets tests swap in an `httpx.MockTransport` so requests
        # never hit the network. It must be given to the AsyncClient
        # constructor itself - reassigning `self._http._transport` after
        # construction does NOT work, because httpx.AsyncClient also keeps a
        # separate `_mounts` table (used for proxy configuration) that is
        # consulted before the default transport and would otherwise still
        # send the request out over the real network.
        # `transport` 是专门给测试用的一个"接口",生产环境的调用方不需要
        # 传它:测试代码传入这个参数,就能换成 `httpx.MockTransport`,
        # 这样请求就完全不会真的打到网络上。它必须在构造 AsyncClient 的
        # 时候就传进去——构造完之后再重新给 `self._http._transport` 赋值
        # 是不管用的,因为 httpx.AsyncClient 还有一张单独的 `_mounts`
        # 表(用于代理配置),这张表会在默认 transport 之前被优先查询,
        # 如果不在构造时传入,请求还是会真的发到网络上。
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def __aenter__(self) -> PetstoreClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Always release the underlying connection pool, even if the caller's
        # `async with` block raised.
        # 无论调用方的 `async with` 代码块里有没有抛异常,都要释放底层的
        # 连接池。
        await self._http.aclose()

    async def list_pets(self, search: PetSearch | None = None) -> list[Pet]:
        """List/search pets. An empty/None search returns every pet.

        Note: petstore-api does not filter out sold pets by default — per
        the onboarding rules ("Already sold pets should not be shown as
        available"), it is the caller's responsibility to pass
        `availability=Availability.available` when that is what the
        customer journey needs. This client does not silently add that
        filter, so behaviour stays predictable and explicit.

        列出/搜索宠物。传空的 search 或者不传,就是返回全部宠物。

        注意:petstore-api 默认不会自动过滤掉已售出的宠物——按照入门项目
        的规则("已售出的宠物不应再显示为可购买"),如果顾客旅程需要这条
        过滤规则,由调用方自己负责传 `availability=Availability.available`。
        这个客户端不会偷偷帮你加上这个过滤条件,这样行为才是可预测、显式的。
        """
        # exclude_none=True: only send query params the caller actually set,
        # so "no filter" really means no filter, not "filter equals None".
        # exclude_none=True:只发送调用方真正设置过的查询参数,这样
        # "没有过滤条件"才真的是"没有过滤条件",而不是"过滤条件等于 None"。
        #
        # mode="json" matters here: Species/Availability are StrEnum
        # subclasses, and this keeps their serialized query value as the
        # plain string ("cat"), matching what Pydantic's JSON mode always
        # produces for enums — the explicit, forward-compatible way to get
        # that string rather than relying on StrEnum's own __str__ behaviour.
        # mode="json" 在这里很关键:Species/Availability 是 StrEnum 的子类,
        # 这样写能让序列化后的查询参数值保持为纯字符串("cat"),这正是
        # Pydantic 在 JSON 模式下处理枚举时始终会得到的结果——这是明确地、
        # 面向未来兼容地拿到这个字符串的写法,而不是依赖 StrEnum 自己的
        # __str__ 行为。
        params = search.model_dump(exclude_none=True, mode="json") if search is not None else {}
        response = await self._request("GET", "/pets", params=params)
        return [Pet.model_validate(item) for item in response.json()]

    async def get_pet(self, pet_id: int) -> Pet:
        """Fetch a single pet's current details.

        Raises PetNotFoundError if no pet with this id exists.

        获取单只宠物的最新详情。

        如果这个 id 对应的宠物不存在,会抛出 PetNotFoundError。
        """
        response = await self._request("GET", f"/pets/{pet_id}", not_found_pet_id=pet_id)
        return Pet.model_validate(response.json())

    async def purchase_pet(self, pet_id: int) -> Order:
        """Attempt to purchase a pet.

        Per the onboarding purchase-safety rules, callers must have already
        obtained explicit customer confirmation *before* calling this — this
        client does not ask for confirmation itself, it only executes the
        purchase attempt and reports the real outcome.

        Raises:
            PetNotFoundError: no pet with this id exists.
            PetNotAvailableError: the pet exists but is pending/sold.

        尝试购买一只宠物。

        按照入门项目的购买安全规则,调用方在调用这个方法之前,必须已经
        拿到了顾客的明确确认——这个客户端本身不会去请求确认,它只负责
        执行这次购买尝试,并如实报告结果。

        可能抛出的异常:
            PetNotFoundError: 这个 id 对应的宠物不存在。
            PetNotAvailableError: 宠物存在,但处于待定/已售出状态。
        """
        response = await self._request("POST", f"/pets/{pet_id}/purchase", not_found_pet_id=pet_id)
        return Order.model_validate(response.json())

    async def _request(
        self,
        method: str,
        path: str,
        *,
        not_found_pet_id: int | None = None,
        # `Any` here (rather than `object`) is a deliberate, narrow exception to
        # strict typing: these kwargs are passed straight through to
        # httpx.AsyncClient.request(), whose accepted types differ per
        # keyword (params vs. json vs. headers, etc.) - re-typing that whole
        # union here would just duplicate httpx's own signature.
        # 这里用 `Any`(而不是 `object`)是刻意对严格类型检查开的一个小口子:
        # 这些关键字参数会原样传给 httpx.AsyncClient.request(),它接受的
        # 类型因关键字而异(params、json、headers 等各不相同)——如果要在
        # 这里重新把这一整套联合类型写一遍,只是在重复 httpx 自己的签名。
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform one HTTP call and translate the outcome into our own
        exception hierarchy before the raw httpx/HTTP details ever leak out.

        `not_found_pet_id`, when given, is only used to build a useful
        PetNotFoundError/PetNotAvailableError message — it does not change
        which status codes are handled.

        发起一次 HTTP 调用,并在原始的 httpx/HTTP 细节泄漏出去之前,把
        结果翻译成我们自己的异常体系。

        `not_found_pet_id` 如果传了,只是用来拼出一条有意义的
        PetNotFoundError/PetNotAvailableError 消息——它不会改变这里处理
        哪些状态码的逻辑。
        """
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.RequestError as exc:
            # DNS failure, connection refused, timeout, etc: the store is
            # simply not reachable right now.
            # DNS 解析失败、连接被拒绝、超时等等:商店现在就是连不上。
            raise StoreUnavailableError(f"Could not reach petstore API: {exc}") from exc

        if response.status_code == 404:
            if not_found_pet_id is not None:
                raise PetNotFoundError(not_found_pet_id)
            raise StoreUnavailableError(f"Unexpected 404 from petstore API: {path}")

        if response.status_code == 409:
            if not_found_pet_id is not None:
                # petstore-api only raises 409 from the purchase endpoint,
                # specifically for "pet exists but is not available".
                # petstore-api 只在购买接口里抛 409,专门对应"宠物存在但
                # 不可购买"这种情况。
                raise PetNotAvailableError(not_found_pet_id)
            raise PurchaseFailedError(response.text)

        if response.status_code == 422:
            raise InvalidRequestError(response.text)

        if response.status_code >= 500:
            raise StoreUnavailableError(f"Petstore API returned {response.status_code}: {response.text}")

        # Any other non-2xx status we did not anticipate: fail loudly rather
        # than silently swallowing it, since httpx.HTTPStatusError is still a
        # useful, honest error to propagate in that unexpected case.
        # 其他任何我们没预料到的非 2xx 状态:宁可让它明显地失败,也不要悄悄
        # 把它吞掉——在这种意外情况下,httpx.HTTPStatusError 仍然是一个
        # 有用、诚实的错误,值得继续往上抛。
        response.raise_for_status()
        return response
