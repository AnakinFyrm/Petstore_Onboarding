"""MCP server for pet-mcp.

Tools are plain typed functions: the docstring and signature are what the client
model sees, so both are part of the interface. Keep them small, pure and
individually testable, and put anything that talks to the outside world behind a
function you can substitute in tests.
工具都是普通的、带类型标注的函数:docstring 和函数签名就是客户端模型能看到的
接口,所以两者都是对外接口的一部分。要把它们写得小、纯粹、可以单独测试,
凡是要跟外部世界打交道的部分,都放到一个测试时可以替换掉的函数背后。

This module exposes exactly the small set of Petstore capabilities the
onboarding spec's customer journey needs (see ONBOARDING.md section 11,
"MCP服务器的职责"): searching/listing pets, fetching one pet's details, and
placing a purchase. Nothing here reaches the database, the filesystem, or a
shell directly - every call goes through pet_client.PetstoreClient, which is
the only thing in this whole system (besides petstore-api itself) allowed to
know petstore-api's URL and HTTP details.
这个模块只暴露入门项目文档里顾客旅程真正需要的这一小组 Petstore 能力
(见 ONBOARDING.md 第 11 节"MCP 服务器的职责"):搜索/列出宠物、获取单只
宠物的详情、发起一次购买。这里没有任何代码直接碰数据库、文件系统或者
shell——每一次调用都要经过 pet_client.PetstoreClient,这是整个系统里
(除了 petstore-api 自己以外)唯一被允许知道 petstore-api 的 URL 和 HTTP
细节的地方。

=== 补充说明(整体导读)===
MCP(Model Context Protocol,模型上下文协议)是一套让"大语言模型"能够
安全地调用"外部工具"的标准协议。这个文件就是用 MCP 官方 Python SDK
(下面 import 的 mcp 这个库)写的一个"MCP 服务器",它只做一件事:
把 pet-client 的三个方法(list_pets/get_pet/purchase_pet),包装成
三个"工具"(search/get/purchase),暴露给外面的 agent 调用。
agent 那边(pet-agent)会把这个服务器当子进程启动,通过 stdio(标准
输入输出)管道跟它通信——agent 发一个"调用工具"的请求过来,这个进程
执行对应的 async 函数,把结果(或者错误)通过同一个管道传回去。
"""

# os 是 Python 标准库,用来读取"环境变量"(比如下面的
# PETSTORE_API_BASE_URL)。
import os
# typing 标准库,Any 表示"任意类型"——下面几个函数返回
# "dict[str, Any]"(键是字符串、值可以是任何类型的字典),因为一只宠物/
# 一笔订单的 JSON 字段值本来就有字符串、数字、列表等各种类型。
from typing import Any

# mcp 是 MCP 协议的官方 Python SDK(第三方库)。
# FastMCP:一个"快速构建 MCP 服务器"的辅助类——只要把普通函数用
# @mcp.tool(...) 装饰一下,FastMCP 就会自动读取函数签名和 docstring,
# 拼成 MCP 协议要求的"工具描述"格式,暴露给客户端(agent)。
from mcp.server.fastmcp import FastMCP
# ToolError:MCP SDK 提供的专用异常类型——在工具函数内部 raise 它,
# SDK 会把这个错误按 MCP 协议规定的格式,包装成一个"工具调用失败"的
# 结果传回给调用方(agent),而不是让整个服务器进程直接崩溃。
from mcp.server.fastmcp.exceptions import ToolError
# ToolAnnotations:MCP 协议里给"每个工具"附加的一组元数据标记(比如
# "这个工具是只读的吗""调用它是否安全、可以重复调用"),帮助调用方
# (agent/它背后的模型)更好地判断什么时候可以放心调用某个工具。
from mcp.types import ToolAnnotations
# 从 pet-client 这个项目里,一次性导入这么多东西:
#   Availability/Species —— 两个枚举类型(库存状态/物种)
#   PetNotAvailableError/PetNotFoundError/PurchaseFailedError/
#   StoreUnavailableError —— 上一个文件(client.py)里讲过的那一套
#     自定义异常
#   PetSearch —— 搜索条件模型
#   PetstoreClient —— 真正发 HTTP 请求的客户端类
# 用括号包起来的多行 import,是 Python 处理"导入的名字太多、一行写不下"
# 时的标准写法,效果跟写在一行上完全一样。
from pet_client import (
    Availability,
    PetNotAvailableError,
    PetNotFoundError,
    PetSearch,
    PetstoreClient,
    PurchaseFailedError,
    Species,
    StoreUnavailableError,
)

# mcp:创建一个 FastMCP 服务器实例,"pet-mcp" 是这个服务器对外报告的名字。
# 后面所有 @mcp.tool(...) 装饰的函数,都会被注册成这个服务器实例暴露的工具。
mcp = FastMCP("pet-mcp")

# Shared annotation sets, per the MCP spec's tool-annotation convention: read
# tools tell the client they are safe to call freely and repeatedly; the
# purchase tool tells the client the opposite (it changes store state and
# cannot be safely retried without side effects).
# 共享的两组标注(annotations),按照 MCP 规范里工具标注的约定:只读工具
# 要告诉客户端"可以放心地反复调用";购买工具则要告诉客户端相反的信息
# (它会改变商店的状态,不能被无副作用地安全重试)。
# _READ_ONLY_ANNOTATIONS:给"只读"工具(搜索、查详情)用的标注——
#   readOnlyHint=True    这个工具不会修改任何状态
#   idempotentHint=True  重复调用多次,效果跟调用一次是一样的
#   openWorldHint=False  这个工具只在一个"封闭"的、已知的数据范围内操作
#                        (不会访问不可预测的外部世界)
_READ_ONLY_ANNOTATIONS = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
# _PURCHASE_ANNOTATIONS:给"购买"这个会产生副作用的工具用的标注——
#   readOnlyHint=False     会修改状态
#   destructiveHint=True   这个操作有"不可逆"的效果(买了就是买了)
#   idempotentHint=False   重复调用不等价于调用一次(第二次购买同一只宠物
#                          会失败,而不是"什么都没发生")
_PURCHASE_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)


# _petstore_client:一个"工厂函数"——每次调用它,都会读取环境变量、
# 造一个新的 PetstoreClient 实例返回。前面下划线开头,表示这是模块内部的
# 辅助函数,不是暴露给 agent 的工具。
def _petstore_client() -> PetstoreClient:
    """Build a PetstoreClient pointed at PETSTORE_API_BASE_URL.

    Kept as its own function (rather than inlined in every tool) for two
    reasons: it is the one place that reads configuration, and tests can
    monkeypatch this single function to inject a client wired to a fake
    transport instead of the real network (see tests/test_server.py).

    构造一个指向 PETSTORE_API_BASE_URL 的 PetstoreClient。

    之所以单独写成一个函数(而不是在每个工具里都写一遍),有两个原因:
    这是唯一一处读取配置的地方;而且测试可以只 monkeypatch 这一个函数,
    换上一个接了假 transport(而不是真实网络)的客户端(见
    tests/test_server.py)。
    """
    # os.environ.get("PETSTORE_API_BASE_URL", "http://localhost:8000"):
    # 读取名为 PETSTORE_API_BASE_URL 的环境变量;如果这个环境变量根本没设置
    # (比如本地随手跑一下,没配置过),就用后面这个默认值
    # "http://localhost:8000" 兜底。
    base_url = os.environ.get("PETSTORE_API_BASE_URL", "http://localhost:8000")
    # 用读到的地址,构造并返回一个新的 PetstoreClient 实例。
    return PetstoreClient(base_url=base_url)


# @mcp.tool(annotations=_READ_ONLY_ANNOTATIONS):把下面这个函数注册成
# 一个 MCP 工具,并附上上面定义的"只读"标注。
@mcp.tool(annotations=_READ_ONLY_ANNOTATIONS)
# pet_mcp_search_pets:第一个工具——搜索/列出宠物。
# 这些参数几乎跟 pet-client 的 PetSearch 模型一模一样,都是 "类型 | None
# = None" 的可选写法——之所以在这里"重复"写一遍(而不是直接把 PetSearch
# 对象当参数),是因为 MCP 协议要求工具参数必须是简单类型(字符串、数字、
# 列表等),模型才能正确地生成调用参数;所以这里保持"扁平"的参数列表,
# 函数体内部再组装成 PetSearch 对象。
async def pet_mcp_search_pets(
    species: Species | None = None,
    breed: str | None = None,
    min_age_months: int | None = None,
    max_age_months: int | None = None,
    min_price_eur: float | None = None,
    max_price_eur: float | None = None,
    availability: Availability | None = None,
    tags: list[str] | None = None,
    name_contains: str | None = None,
# 返回类型 list[dict[str, Any]]:一个"字典组成的列表",每个字典是一只
# 宠物的字段(MCP 协议要求工具返回的是可以直接序列化成 JSON 的普通数据,
# 不能直接返回一个 Pydantic 对象)。
) -> list[dict[str, Any]]:
    """Search or list pets in the Petstore, filtered by any combination of criteria.

    Leave every argument unset to list the whole current inventory. Results
    always come straight from the Petstore API - nothing here is invented.
    To only see pets a customer could actually buy right now, pass
    availability="available".

    在 Petstore 里搜索或列出宠物,可以按任意组合的条件过滤。

    所有参数都不传,就是列出当前的全部库存。返回结果永远直接来自
    Petstore API——这里不会编造任何数据。如果只想看现在真的可以卖给
    顾客的宠物,传 availability="available"。
    """
    # 用收到的这些扁平参数,组装成一个 pet-client 认识的 PetSearch 对象——
    # 这一步会触发 pet-client 的 models.py 里 PetSearch 模型自己的校验
    # (不过那边的校验比较宽松,真正严格的校验规则其实在 petstore-api
    # 那一层——这里更多是把参数"打包"成结构化对象)。
    search = PetSearch(
        species=species,
        breed=breed,
        min_age_months=min_age_months,
        max_age_months=max_age_months,
        min_price_eur=min_price_eur,
        max_price_eur=max_price_eur,
        availability=availability,
        tags=tags,
        name_contains=name_contains,
    )
    # try/except:把真正调用 pet-client 的这一步包起来,专门捕获
    # "商店不可用"这一种异常(搜索这个动作本身不会命中"未找到""不可购买"
    # 这些异常,所以这里只需要处理连接失败/服务器出错这一种情况)。
    try:
        # "async with _petstore_client() as client:"——每次调用这个工具,
        # 都新建一个 PetstoreClient(见上面的 _petstore_client 函数),
        # 用 async with 语法保证用完之后一定会正确关闭连接(对应 client.py
        # 里的 __aenter__/__aexit__)。
        async with _petstore_client() as client:
            # 调用 pet-client 的 list_pets 方法,真正发起一次
            # GET /pets 请求,拿到 Pet 对象组成的列表。
            pets = await client.list_pets(search)
    except StoreUnavailableError as exc:
        # Re-raised as ToolError so the agent gets a clear, expected failure
        # mode it can honestly relay to the customer, instead of a raw
        # connection-error stack trace.
        # 重新抛成 ToolError,让 agent 拿到一个清晰的、预期内的失败情况,
        # 可以如实转达给顾客,而不是一个原始的连接错误堆栈。
        # f"STORE_UNAVAILABLE: {exc}":用一个"约定俗成的错误码前缀"
        # (STORE_UNAVAILABLE)拼在错误信息最前面——这样 agent(背后的 LLM)
        # 看到这个字符串,能一眼识别出"这是哪一类失败",而不用去解析自由
        # 格式的英文句子。
        raise ToolError(f"STORE_UNAVAILABLE: {exc}") from exc

    # 一切正常:用一个列表推导式,把每一个 Pet 对象(Pydantic 模型)转换成
    # 普通字典(mode="json" 保证枚举等特殊类型也被转换成普通的 JSON 兼容值,
    # 比如 Species.dog 变成字符串 "dog"),再把这些字典组成的列表返回。
    return [pet.model_dump(mode="json") for pet in pets]


# @mcp.tool(annotations=_READ_ONLY_ANNOTATIONS):第二个只读工具。
@mcp.tool(annotations=_READ_ONLY_ANNOTATIONS)
# pet_mcp_get_pet:按 id 查一只宠物的详情。
async def pet_mcp_get_pet(pet_id: int) -> dict[str, Any]:
    """Fetch one pet's current details, including its live price and availability.

    Always call this immediately before showing a customer a pet's price or
    availability, and again immediately before a purchase attempt - stored
    conversation state can go stale, but this call never does.

    获取单只宠物的最新详情,包括它当前的价格和可购买状态。

    在向顾客展示某只宠物的价格或可购买状态之前,一定要先调用这个工具;
    在真正尝试购买之前,也要再调用一次——对话里存下来的状态可能是过时的,
    但这次调用得到的结果永远不会过时。
    """
    try:
        async with _petstore_client() as client:
            # 调用 pet-client 的 get_pet 方法,发起 GET /pets/{pet_id}。
            pet = await client.get_pet(pet_id)
    # 捕获"这个 id 对应的宠物根本不存在"的情况。
    except PetNotFoundError as exc:
        raise ToolError(f"PET_NOT_FOUND: {exc}") from exc
    # 捕获"商店连不上/出错"的情况。
    except StoreUnavailableError as exc:
        raise ToolError(f"STORE_UNAVAILABLE: {exc}") from exc

    # 把查到的这一只 Pet 对象转换成普通字典返回。
    return pet.model_dump(mode="json")


# @mcp.tool(annotations=_PURCHASE_ANNOTATIONS):第三个工具,注意用的是
# 上面定义的"购买"专用标注(会改变状态、不可安全重试)。
@mcp.tool(annotations=_PURCHASE_ANNOTATIONS)
# pet_mcp_purchase_pet:代表顾客购买一只宠物。
# confirm: bool:这个参数没有默认值,意味着调用方必须显式传一个
# True/False——这本身也是"确认关卡"设计的一部分:不能靠"不传这个参数"
# 就蒙混过关(因为它是必填的)。
async def pet_mcp_purchase_pet(pet_id: int, confirm: bool) -> dict[str, Any]:
    """Purchase a pet on the customer's behalf. Requires confirm=True.

    Before calling this with confirm=True, you MUST already have: called
    pet_mcp_get_pet to show the customer this pet's current name, price and
    availability, and received the customer's explicit confirmation to buy it
    at that price (a vague "sounds good" is not enough - see the onboarding
    spec's confirmation rules). Calling this with confirm=False (or omitting
    it) is rejected before any purchase is attempted, so it is always safe to
    call once first just to double-check the gate is in place.

    The price charged is always whatever petstore-api currently has on file -
    this tool has no way to accept or use a price you supply. Availability is
    re-checked by petstore-api at the moment of purchase, so a pet that went
    from available to sold between your last pet_mcp_get_pet call and now
    will correctly fail here rather than appearing to succeed.

    代表顾客购买一只宠物。必须传 confirm=True 才会真的执行购买。

    在传 confirm=True 调用这个工具之前,你必须已经做到:调用过
    pet_mcp_get_pet,向顾客展示过这只宠物当前的名字、价格和可购买状态,
    并且已经得到顾客对"以这个价格购买"的明确确认(一句含糊的"听起来不错"
    是不够的——见入门项目文档里的确认规则)。如果传 confirm=False(或者
    干脆不传),在真正尝试购买之前就会被拒绝——所以先单独调用一次来确认
    这道"确认关卡"确实生效,是完全安全的。

    实际扣的价格永远是 petstore-api 当前记录的价格——这个工具没有任何
    办法接受或使用你自己提供的价格。可购买状态会在购买的那一刻由
    petstore-api 重新核查一遍,所以如果一只宠物在你上一次调用
    pet_mcp_get_pet 之后、到现在之间,从"可购买"变成了"已售出",
    这里会正确地失败,而不会看起来像是购买成功了。
    """
    # 这是整个购买流程里最关键的一道"代码层面的关卡"——
    # "not confirm":如果 confirm 是 False(或者虽然是必填参数,但调用方
    # 传了 False),这个条件为真,直接拒绝,不会往下走到真正调用
    # purchase_pet 的那一步。
    if not confirm:
        # The confirmation gate lives here, in code, not just in this
        # docstring's instructions - an agent that ignores the docstring and
        # calls with confirm=False (or the default) still cannot buy anything.
        # 确认关卡是写在这里的代码里的,不只是写在上面这段 docstring 的
        # 说明文字里——就算 agent 没理会 docstring、直接用 confirm=False
        # (或者默认值)来调用,也一样买不成任何东西。
        # 抛出 ToolError,错误码前缀是 CONFIRMATION_REQUIRED,消息里直接
        # 告诉 agent 正确的操作顺序应该是什么(先查详情、拿到顾客确认、
        # 再带 confirm=True 重新调用一次)——这段说明本身也是"喂给"
        # 背后大语言模型的提示词的一部分。
        raise ToolError(
            "CONFIRMATION_REQUIRED: call pet_mcp_get_pet first to show the customer this "
            "pet's current name, price and availability, get their explicit confirmation to "
            "buy it at that price, then call pet_mcp_purchase_pet again with confirm=True."
        )

    # 走到这里说明 confirm=True,可以真正尝试购买了。
    try:
        async with _petstore_client() as client:
            # 调用 pet-client 的 purchase_pet 方法,发起
            # POST /pets/{pet_id}/purchase。
            order = await client.purchase_pet(pet_id)
    # 依次捕获"未找到""不可购买""购买失败(其他原因)""商店不可用"
    # 这四种可能的异常,分别翻译成带不同错误码前缀的 ToolError——
    # 这四行的结构几乎一样,唯一的区别就是捕获的异常类型和对应的错误码前缀,
    # 让 agent 能精确区分到底是哪一类失败。
    except PetNotFoundError as exc:
        raise ToolError(f"PET_NOT_FOUND: {exc}") from exc
    except PetNotAvailableError as exc:
        raise ToolError(f"PET_NOT_AVAILABLE: {exc}") from exc
    except PurchaseFailedError as exc:
        raise ToolError(f"PURCHASE_FAILED: {exc}") from exc
    except StoreUnavailableError as exc:
        raise ToolError(f"STORE_UNAVAILABLE: {exc}") from exc

    # 购买成功,把订单对象转换成普通字典返回给 agent。
    return order.model_dump(mode="json")


# main:这个模块作为一个独立程序启动时,真正的入口函数。
def main() -> None:
    """Run the MCP server over stdio.

    以 stdio 方式运行这个 MCP 服务器。
    """
    # mcp.run():FastMCP 提供的方法——默认按 stdio(标准输入/标准输出)
    # 的方式运行这个服务器:不断从标准输入读取 agent 发来的 MCP 协议消息
    # (调用哪个工具、带什么参数),执行对应的函数,把结果写回标准输出。
    # 这正是 pet-agent 之所以能把这个服务器"当一个子进程启动"、通过管道
    # 通信的原因——完全不需要监听网络端口。
    mcp.run()


# Python 的标准写法:只有当这个文件是被"直接运行"(比如
# `python server.py` 或者被打包成命令行入口点执行),
# __name__ 这个内置变量的值才会是字符串 "__main__";如果这个文件是被
# "当作一个模块 import 进别的代码里",__name__ 就会是模块的实际名字
# (比如 "pet_mcp.server"),下面这行就不会执行——这样写的好处是:
# 这个文件既可以被直接运行,也可以被别的代码安全地 import 使用,而不会
# 在 import 的时候就意外地把服务器跑起来。
if __name__ == "__main__":
    main()
