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

=== 补充说明(为方便理解新加的整体导读) ===
这个文件是"pet-client"这个项目里唯一真正发起 HTTP 请求的地方。
可以把它理解成:MCP 服务器(pet-mcp)想找 petstore-api 要数据,
从来不会自己拼 URL、自己处理状态码,而是永远只调用这里的
list_pets()/get_pet()/purchase_pet() 这三个方法——这三个方法内部
再统一去调用私有的 _request(),由 _request() 把 httpx 库返回的
"HTTP 世界的东西"(状态码、httpx 自己的异常)翻译成
exceptions.py 里定义的"Petstore 世界的东西"
(PetNotFoundError/PetNotAvailableError/InvalidRequestError/
StoreUnavailableError/PurchaseFailedError)。
"""

# types 是 Python 标准库,TracebackType 是"异常回溯信息"的类型——
# 下面 __aexit__ 方法的参数会用到它,用来做类型注解。
from types import TracebackType
# typing 标准库,Any 表示"任意类型"——下面 _request 方法的 **kwargs
# 会用到,因为不同的 HTTP 参数(params/json/headers 等)类型都不一样。
from typing import Any

# httpx 是一个第三方 HTTP 客户端库,类似 requests,但原生支持 async/await
# ——这也是为什么整个项目选它而不是更常见的 requests(requests 是纯同步的,
# 会阻塞异步事件循环)。
import httpx

# 从本项目自己的 exceptions.py 里导入五个自定义异常类——它们的具体定义和
# 各自对应的触发条件,已经在这个文件自己的模块级文档字符串里写清楚了,
# 这里只需要知道:_request() 方法会把 httpx 层面的各种失败,分别翻译成
# 下面这五种之一再往外抛。
from pet_client.exceptions import (
    InvalidRequestError,
    PetNotAvailableError,
    PetNotFoundError,
    PurchaseFailedError,
    StoreUnavailableError,
)
# 从本项目自己的 models.py 里导入三个 Pydantic 模型:Order(订单)、
# Pet(宠物)、PetSearch(搜索条件)——用来把 HTTP 响应的原始 JSON,
# 解析成有类型、有字段提示的 Python 对象。
from pet_client.models import Order, Pet, PetSearch


# PetstoreClient:整个客户端类,封装了"怎么跟 petstore-api 说话"这件事。
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

    # __init__:构造函数,每次 "PetstoreClient(...)" 被调用时执行这里的代码。
    def __init__(
        self,
        # base_url:petstore-api 的根地址,比如 "http://petstore-api:8000"。
        base_url: str,
        # timeout:请求超时时间(秒),默认给 5.0 秒,超过这个时间还没响应
        # 就会被 httpx 判定为超时(在 _request 里会被当成 StoreUnavailableError
        # 处理,见下方)。
        timeout: float = 5.0,
        # "*" 单独一个星号:强制它后面的参数(这里是 transport)必须以
        # "关键字参数"的形式传(比如 transport=xxx),不能按位置传——
        # 这是一种 API 设计上的保护,避免调用方不小心按错误的顺序传参。
        *,
        # transport:测试专用的"钩子",生产环境用不到,默认是 None。
        transport: httpx.AsyncBaseTransport | None = None,
    # 返回类型注解 "-> None":__init__ 方法本身不返回任何有意义的值
    # (它的"返回值"体现在把 self 上的属性设置好)。
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
        # self._http:把创建好的 httpx.AsyncClient 实例,存成这个对象自己
        # 的一个属性(用下划线开头,表示这是"内部实现细节",不希望外部
        # 代码直接访问)——后面所有的方法都通过 self._http 发请求。
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    # __aenter__:Python 的"异步上下文管理器"协议方法之一——
    # 当外部代码写 "async with PetstoreClient(...) as client:" 时,
    # Python 会自动调用这个方法,它的返回值就赋给 "as" 后面的变量。
    # 返回类型注解用了字符串 "PetstoreClient"(前向引用),因为在类自己
    # 的定义体内部,类本身还没有定义完。
    async def __aenter__(self) -> PetstoreClient:
        # 直接返回自身,意味着 "async with ... as client" 里的 client
        # 就是这个 PetstoreClient 实例本身。
        return self

    # __aexit__:配套的"退出"方法——当 "async with" 代码块结束时
    # (无论正常结束还是因为异常提前结束)都会被自动调用。
    async def __aexit__(
        self,
        # 下面三个参数是 Python 上下文管理器协议的固定格式:如果代码块内
        # 抛了异常,这三个参数会分别是异常的类型、异常对象本身、和
        # traceback(异常发生的调用栈信息);如果没抛异常,三个都是 None。
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # Always release the underlying connection pool, even if the caller's
        # `async with` block raised.
        # 无论调用方的 `async with` 代码块里有没有抛异常,都要释放底层的
        # 连接池。
        # await self._http.aclose():异步地关闭这个共享的 HTTP 客户端,
        # 释放它占用的连接池资源——这就是为什么整个客户端要设计成
        # "async with" 用法,保证不会忘记清理连接。
        await self._http.aclose()

    # list_pets:对外暴露的第一个方法——列出/搜索宠物。
    # search: PetSearch | None = None:搜索条件是可选的,不传就是 None,
    # 意味着"不加任何过滤条件"。
    # 返回类型 list[Pet]:一个 Pet 对象组成的列表。
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
        # 这一行:如果 search 不是 None,就把它 "拍平" 成一个字典
        # (只包含非 None 的字段);如果 search 本身就是 None(调用方完全
        # 没传搜索条件),params 就是一个空字典 {}。
        params = search.model_dump(exclude_none=True, mode="json") if search is not None else {}
        # await self._request(...):调用下面定义的私有方法 _request,
        # 真正发起一次 GET /pets 请求,把 params 作为查询参数传过去。
        # 这个方法的返回值是一个 httpx.Response 对象(已经确认过状态码正常)。
        response = await self._request("GET", "/pets", params=params)
        # response.json():把响应体解析成 Python 的原始数据(这里应该是
        # 一个"字典组成的列表",每个字典是一只宠物的原始 JSON 字段)。
        # 用一个"列表推导式":对这个列表里的每一个 item(原始字典),
        # 调用 Pet.model_validate(item),把它转换/校验成一个真正的 Pet
        # 对象,最终返回的是"Pet 对象组成的列表"。
        return [Pet.model_validate(item) for item in response.json()]

    # get_pet:对外暴露的第二个方法——按 id 查一只具体的宠物详情。
    async def get_pet(self, pet_id: int) -> Pet:
        """Fetch a single pet's current details.

        Raises PetNotFoundError if no pet with this id exists.

        获取单只宠物的最新详情。

        如果这个 id 对应的宠物不存在,会抛出 PetNotFoundError。
        """
        # 调用 _request 发起 GET /pets/{pet_id} 请求。
        # f"/pets/{pet_id}":f-string 把 pet_id 的实际值嵌入 URL 路径里,
        # 比如 pet_id=7 就会请求 "/pets/7"。
        # not_found_pet_id=pet_id:把这个 id 传给 _request,这样如果服务端
        # 返回 404,_request 就能拼出一条"哪个 id 没找到"的有意义错误信息
        # (具体见 _request 内部的实现)。
        response = await self._request("GET", f"/pets/{pet_id}", not_found_pet_id=pet_id)
        # 把响应体的 JSON 解析、校验成一个 Pet 对象并返回。
        return Pet.model_validate(response.json())

    # purchase_pet:对外暴露的第三个方法——尝试购买一只宠物。
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
        # 发起 POST /pets/{pet_id}/purchase 请求——这个方法本身不接收/不要求
        # "confirm" 参数,方法的注释里明确写了:是否确认购买这件事,应该由
        # 调用方(pet-mcp 的工具函数)在调用这个方法之前就已经处理好。
        response = await self._request("POST", f"/pets/{pet_id}/purchase", not_found_pet_id=pet_id)
        # 把响应体解析、校验成一个 Order(订单)对象并返回。
        return Order.model_validate(response.json())

    # _request:私有的核心方法(名字前面的下划线是 Python 里"这是内部实现,
    # 请不要在类外部直接调用"的约定俗成写法)。上面三个公开方法全部通过它
    # 来真正发出 HTTP 请求。
    async def _request(
        self,
        # method:HTTP 方法,比如 "GET"、"POST"。
        method: str,
        # path:请求路径,比如 "/pets" 或者 "/pets/7/purchase"。
        path: str,
        # "*" 同上,强制后面的参数必须用关键字传递。
        *,
        # not_found_pet_id:可选,只是用来在报错信息里带上"是哪个 id"。
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
        # **kwargs:Python 语法,"收集所有其余的关键字参数,打包成一个字典"
        # ——这样 list_pets 传的 params=xxx 会被收进 kwargs 字典里,
        # 再原样转发给 httpx。
        **kwargs: Any,
    # 返回类型 httpx.Response:这个方法返回的是"确认过状态码没问题"的
    # 原始 httpx 响应对象,具体怎么解析成 Pet/Order 交给调用它的方法自己做。
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
        # try/except:把真正发起网络请求这一步包起来,因为网络层面的失败
        # (连不上、超时)跟"服务器正常响应但返回了错误状态码"是两种完全
        # 不同性质的问题,要分开处理。
        try:
            # self._http.request(method, path, **kwargs):真正调用 httpx
            # 库发起这次 HTTP 请求,await 等待它完成并拿到响应。
            response = await self._http.request(method, path, **kwargs)
        # httpx.RequestError:httpx 库定义的"请求层面出问题"的异常基类,
        # 覆盖了 DNS 解析失败、连接被拒绝、超时等各种"根本没能完成这次
        # HTTP 交互"的情况(注意:这跟"服务器返回了 500"是不同的,那种
        # 情况请求已经完成了,只是响应内容不好)。
        except httpx.RequestError as exc:
            # DNS failure, connection refused, timeout, etc: the store is
            # simply not reachable right now.
            # DNS 解析失败、连接被拒绝、超时等等:商店现在就是连不上。
            # 把这种"连不上"的情况,统一翻译成我们自己的 StoreUnavailableError,
            # "from exc" 保留原始异常作为这个新异常的"来源",方便调试。
            raise StoreUnavailableError(f"Could not reach petstore API: {exc}") from exc

        # 走到这里说明请求已经成功"打了个来回"(拿到了响应),接下来根据
        # HTTP 状态码,分别翻译成不同的自定义异常。

        # 404:资源未找到。
        if response.status_code == 404:
            # 如果调用时带了 not_found_pet_id(说明这是一次"查某个具体
            # pet_id"的请求),就抛出 PetNotFoundError,把这个 id 带上,
            # 方便上层拼出"宠物 X 未找到"这种有意义的消息。
            if not_found_pet_id is not None:
                raise PetNotFoundError(not_found_pet_id)
            # 如果连 pet_id 上下文都没有,却收到了 404,说明这是一个我们
            # 没预料到的情况(不属于已知的业务场景),保守地当成"商店不可用"
            # 处理,而不是假装知道发生了什么。
            raise StoreUnavailableError(f"Unexpected 404 from petstore API: {path}")

        # 409:资源状态冲突——对应 main.py 里"宠物存在但不可购买"的场景。
        if response.status_code == 409:
            if not_found_pet_id is not None:
                # petstore-api only raises 409 from the purchase endpoint,
                # specifically for "pet exists but is not available".
                # petstore-api 只在购买接口里抛 409,专门对应"宠物存在但
                # 不可购买"这种情况。
                raise PetNotAvailableError(not_found_pet_id)
            # 同样地,如果没有 pet_id 上下文却收到 409,归类为
            # PurchaseFailedError(而不是随便套用 PetNotAvailableError),
            # 因为这属于"确实是购买失败,但原因没法精确归类"的情况。
            raise PurchaseFailedError(response.text)

        # 422:请求本身格式/内容不合法(校验失败)。
        if response.status_code == 422:
            # response.text:响应体的原始文本内容(通常是 FastAPI 生成的、
            # 描述校验失败原因的 JSON 字符串),直接作为 detail 传给
            # InvalidRequestError。
            raise InvalidRequestError(response.text)

        # >= 500:服务器自身出错(比如数据库连不上、代码抛了未处理的异常),
        # 一律归类为"商店当前不可用"。
        if response.status_code >= 500:
            raise StoreUnavailableError(f"Petstore API returned {response.status_code}: {response.text}")

        # Any other non-2xx status we did not anticipate: fail loudly rather
        # than silently swallowing it, since httpx.HTTPStatusError is still a
        # useful, honest error to propagate in that unexpected case.
        # 其他任何我们没预料到的非 2xx 状态:宁可让它明显地失败,也不要悄悄
        # 把它吞掉——在这种意外情况下,httpx.HTTPStatusError 仍然是一个
        # 有用、诚实的错误,值得继续往上抛。
        # response.raise_for_status():httpx 自带的方法——如果状态码不是
        # 2xx(成功范围),就抛出 httpx.HTTPStatusError;如果是 2xx,
        # 这行什么都不做,直接往下走。走到这里的状态码理论上只剩下 2xx
        # 或者极少数没被上面分支覆盖到的非 2xx,所以这行是最后的安全网。
        response.raise_for_status()
        # 一路顺利通过上面所有检查,说明这是一次成功的请求,把原始的
        # httpx.Response 对象返回给调用方(list_pets/get_pet/purchase_pet),
        # 由它们各自负责把 JSON 解析成具体的模型对象。
        return response
