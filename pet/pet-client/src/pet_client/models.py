"""Domain models for the Petstore client.

These models are a deliberate *mirror* of the Pydantic schemas defined in the
petstore-api project (see app/schemas.py there), not an import of them. The
client and the API are two separate deployables running in two separate
processes/containers, so they cannot share a Python import at runtime — the
only thing they share is the *shape* of the data flowing over HTTP.
本模块的模型是刻意"镜像"petstore-api 项目里定义的 Pydantic schema(见那边的
app/schemas.py),而不是直接 import 它们。客户端和 API 是两个独立的部署单元,
运行在两个独立的进程/容器里,运行时没法共享同一个 Python import——它们唯一
共享的是通过 HTTP 传输的数据"形状"。

Keeping a client-side copy of these models also matches the architectural
boundary described in the onboarding spec: everything downstream of this
client (the MCP server, the agent, eventually the CLI) should work with clear
Petstore concepts ("a Pet", "a search", "an Order") instead of touching raw
JSON dictionaries coming back from `httpx`.
在客户端这边保留一份模型副本,也符合入门项目文档里描述的架构边界:这个客户端
下游的所有组件(MCP 服务器、agent,以后还有 CLI)都应该基于清晰的 Petstore
概念("一只宠物"、"一次搜索"、"一个订单")来工作,而不是直接处理 `httpx`
返回的原始 JSON 字典。

Validation responsibility: the *source of truth* for what makes a Pet valid
lives in petstore-api. These models are not meant to re-implement business
rules (e.g. "tail_length_cm must be >= 1") — the API already rejects invalid
data before it is ever persisted. Here we mainly need enough structure so
that a well-formed API response gets parsed into a typed, IDE-friendly
object instead of being passed around as `dict[str, Any]`.
校验职责:"什么样的宠物数据算合法"这件事的事实来源(source of truth)在
petstore-api 那边。这些模型不是用来重新实现业务规则的(比如"尾长必须
大于等于 1 厘米")——API 已经在数据落库之前把非法数据拒绝掉了。这里的模型
主要是提供足够的结构,让一个格式正确的 API 响应能被解析成一个有类型、
IDE 友好的对象,而不是当作 `dict[str, Any]` 到处传递。
"""

from enum import StrEnum

from pydantic import BaseModel


class Species(StrEnum):
    """Broad species category, mirrors petstore-api's Species enum.

    大类物种,镜像 petstore-api 里的 Species 枚举。
    """

    dog = "dog"
    cat = "cat"
    rabbit = "rabbit"
    bird = "bird"
    reptile = "reptile"
    other = "other"


class Availability(StrEnum):
    """Purchase status of a pet, mirrors petstore-api's Availability enum.

    宠物的可购买状态,镜像 petstore-api 里的 Availability 枚举。
    """

    available = "available"
    pending = "pending"
    sold = "sold"


class Pet(BaseModel):
    """A single pet record as returned by GET /pets and GET /pets/{pet_id}.

    Field types here are intentionally permissive (e.g. `str | None` for
    optional fields) — strict validation already happened server-side. We
    are just describing the response shape, not re-validating it.

    单条宠物记录,对应 GET /pets 和 GET /pets/{pet_id} 的返回结果。

    这里的字段类型故意写得比较宽松(比如可选字段用 `str | None`)——严格的
    校验已经在服务端做过了。这里只是在描述响应的形状,不是重新校验一遍。
    """

    id: int
    name: str
    species: Species
    # Required by petstore-api only when species == Species.other, but the
    # API itself enforces that rule; here it is simply optional so we can
    # parse both cases.
    # 只有当 species == Species.other 时,petstore-api 才要求必填这个字段,
    # 但这条规则是 API 自己强制执行的;这里只是把它设为可选,方便两种情况
    # 都能正常解析。
    specific_species: str | None = None
    breed: str | None = None
    age_months: int
    weight_kg: float
    tail_length_cm: float
    description: str
    price_eur: float
    availability: Availability
    tags: list[str]
    photo_references: list[str]


class PetSearch(BaseModel):
    """Search criteria sent as query parameters to GET /pets.

    All fields are optional: an empty PetSearch() means "no filter, list
    everything". `model_dump(exclude_none=True)` (used in client.py) turns
    this into just the query parameters the caller actually specified.

    发送给 GET /pets 的搜索条件,会被当作查询参数传过去。

    所有字段都是可选的:一个空的 PetSearch() 意味着"不加任何过滤条件,
    列出全部"。client.py 里用的 `model_dump(exclude_none=True)` 会把它
    转换成调用方实际设置过的那些查询参数。
    """

    species: Species | None = None
    breed: str | None = None
    min_age_months: int | None = None
    max_age_months: int | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    availability: Availability | None = None
    tags: list[str] | None = None
    name_contains: str | None = None


class PurchaseRequest(BaseModel):
    """Body/identifier for a purchase attempt.

    Kept as its own model (rather than just passing an int) so the shape of
    "what a purchase needs" is explicit and can grow later (e.g. an
    idempotency key) without changing every call site's signature.

    一次购买尝试所需的标识信息。

    之所以单独做成一个模型(而不是直接传一个 int),是为了让"一次购买
    需要什么信息"这件事的形状是显式的,以后如果要加字段(比如幂等键)
    也不用改每一个调用点的函数签名。
    """

    pet_id: int


class Order(BaseModel):
    """A successful purchase result, as returned by POST /pets/{pet_id}/purchase.

    Per the onboarding rules, the price here always comes from the store
    (petstore-api) — the agent/client must never invent or override it.

    一次成功的购买结果,对应 POST /pets/{pet_id}/purchase 的返回。

    按照入门项目的规则,这里的价格永远来自商店(petstore-api)——agent/
    客户端绝不能自己编造或覆盖这个价格。
    """

    id: int
    pet_id: int
    price_eur: float
