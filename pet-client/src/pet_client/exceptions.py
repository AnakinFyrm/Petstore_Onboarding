"""Application-level exceptions for the Petstore client.

The whole point of this module is translation: httpx-level failures (a
connection error, a timeout, an HTTP status code) get turned into a small,
closed set of exceptions that describe *what happened in Petstore terms*.
Callers of PetstoreClient (the MCP server's tool functions, eventually)
should only ever need to catch these — never `httpx.HTTPStatusError` or
`httpx.RequestError` directly.
本模块的核心作用是"翻译":把 httpx 层面的失败(连接错误、超时、HTTP 状态码)
转换成一小组固定的、用"Petstore 的语言"描述"到底发生了什么"的异常。
PetstoreClient 的调用方(以后是 MCP 服务器的工具函数)应该只需要捕获这些
异常——永远不用直接处理 `httpx.HTTPStatusError` 或 `httpx.RequestError`。

Keeping this hierarchy small and closed also matches the onboarding
requirement that the agent must be able to "honestly explain success and
failure" — a small set of well-named exceptions is much easier to turn into
a clear customer-facing message than raw HTTP details.
把这套异常体系保持得小而封闭,也符合入门项目里"agent 必须能诚实地解释
成功和失败"这条要求——一小组命名清晰的异常,比原始的 HTTP 细节要容易得多
地转换成清晰的面向顾客的消息。
"""


class PetstoreClientError(Exception):
    """Base class for every exception raised by PetstoreClient.

    Catching this alone is enough for a caller that just wants to know
    "something about talking to the store failed", without caring about the
    specific reason.

    所有 PetstoreClient 抛出的异常的基类。

    如果调用方只想知道"跟商店通信这件事失败了",而不关心具体原因,
    只捕获这一个基类就够了。
    """


class PetNotFoundError(PetstoreClientError):
    """Raised when petstore-api returns 404 for a pet_id.

    Maps to: GET /pets/{pet_id} -> 404, POST /pets/{pet_id}/purchase -> 404.

    当 petstore-api 针对某个 pet_id 返回 404 时抛出。

    对应关系:GET /pets/{pet_id} -> 404,POST /pets/{pet_id}/purchase -> 404。
    """

    def __init__(self, pet_id: int) -> None:
        self.pet_id = pet_id
        super().__init__(f"Pet {pet_id} not found")


class PetNotAvailableError(PetstoreClientError):
    """Raised when a purchase is attempted on a pet that is not available.

    Maps to: POST /pets/{pet_id}/purchase -> 409 (petstore-api raises this
    specifically when crud.PetNotAvailableError bubbles up — see
    petstore-api/app/main.py). This is the case where the pet exists but is
    already "pending" or "sold".

    当尝试购买一只当前不可购买的宠物时抛出。

    对应关系:POST /pets/{pet_id}/purchase -> 409(petstore-api 是在
    crud.PetNotAvailableError 冒泡上来时专门抛出这个状态码的——见
    petstore-api/app/main.py)。这种情况是宠物本身存在,但已经是
    "待定(pending)"或"已售出(sold)"状态了。
    """

    def __init__(self, pet_id: int) -> None:
        self.pet_id = pet_id
        super().__init__(f"Pet {pet_id} is not available for purchase")


class InvalidRequestError(PetstoreClientError):
    """Raised when the request itself was rejected as malformed.

    Maps to: any endpoint -> 422. This covers both petstore-api's own
    `schemas.PetSearch` validation errors and FastAPI's built-in query
    parameter validation (e.g. min_age_months must be >= 0).

    当请求本身因为格式不合法而被拒绝时抛出。

    对应关系:任意接口 -> 422。这既包括 petstore-api 自己的
    `schemas.PetSearch` 校验错误,也包括 FastAPI 内置的查询参数校验
    (比如 min_age_months 必须 >= 0)。
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Invalid request: {detail}")


class StoreUnavailableError(PetstoreClientError):
    """Raised when petstore-api could not be reached at all, or returned a
    5xx server error.

    This is the "I currently cannot connect to the store" case from the
    onboarding spec's example conversations — the assistant must say this
    plainly rather than pretending the store is working.

    当完全连不上 petstore-api,或者它返回 5xx 服务器错误时抛出。

    这对应入门项目示例对话里"我目前无法连接到宠物商店"这种情况——助手
    必须坦率地说明这一点,而不能假装商店在正常工作。
    """


class PurchaseFailedError(PetstoreClientError):
    """Raised when a purchase attempt failed for a reason that is not
    "pet not found" and not "pet not available" (e.g. an unexpected 409
    without a recognised pet_id context, or another business-rule
    rejection). Kept separate from PetNotAvailableError so callers can
    still special-case the common "already sold" outcome precisely.

    当一次购买尝试失败,但原因既不是"宠物未找到"也不是"宠物不可购买"时
    抛出(比如一个没有可识别 pet_id 上下文的意外 409,或者其他业务规则
    拒绝)。之所以跟 PetNotAvailableError 分开,是为了让调用方仍然能够
    精确地单独处理"已售出"这个最常见的失败情况。
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Purchase failed: {detail}")
