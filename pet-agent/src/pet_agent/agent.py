"""The Pydantic AI Petstore assistant, hosted in pet-aes.

Every action the assistant can take comes from the pet-mcp MCP server, reached
over stdio as a subprocess this module launches - there are no local
``@agent.tool`` functions here on purpose, so "use the MCP server, never
bypass it" (ONBOARDING.md section 10, "Agent 不得...绕开 MCP 服务器") is true
by construction, not by discipline. This module never imports pet_mcp or
pet_client, and never talks to petstore-api or a database directly.

Per ONBOARDING.md section 12, step 7, this module no longer builds a
``pydantic_ai.Agent`` directly or manages its own session class - it declares
``PETSTORE_AGENT_SPEC`` (a ``pet_aes.AgentSpec``: prompt + the pet-mcp tool
names this agent is allowed to use) and hands the actual building and running
to ``pet_aes``. ``pet_aes.build_agent`` turns the spec into an ``Agent``,
filtering the MCP toolset down to exactly the names the spec declares;
``pet_aes.HostedAgentService`` is the operational boundary a caller (this
module's own ``run_agent``, the CLI, a future HTTP listener) talks to instead
of calling ``agent.run()`` itself - which is what makes "CLI 应当通过 AES 进行
通信,而不是自己直接创建或运行该 agent" (ONBOARDING.md's own wording) true in
code, not just in a document.

本模块是 Petstore 助手真正的核心。助手能执行的每一个动作都来自 pet-mcp 这个
MCP 服务器,以 stdio 方式作为子进程被本模块启动 —— 这里故意没有写任何本地的
``@agent.tool`` 函数,这样"使用 MCP 服务器、绝不绕开它"
(见 ONBOARDING.md 第 10 节,"Agent 不得……绕开 MCP 服务器")就是代码结构本身
保证的,而不是靠自觉遵守。本模块从来不 import pet_mcp 或 pet_client,也从来
不直接跟 petstore-api 或数据库打交道。

按 ONBOARDING.md 第 12 节第 7 步的要求,本模块不再自己直接构建
``pydantic_ai.Agent``,也不再自己维护一个 session 类 —— 它只声明
``PETSTORE_AGENT_SPEC``(一个 ``pet_aes.AgentSpec``:提示词 + 这个 agent 被
允许使用的 pet-mcp 工具名),把真正"怎么构建"和"怎么运行"都交给 ``pet_aes``。
``pet_aes.build_agent`` 把这份 spec 变成一个 ``Agent``,并把 MCP toolset 过滤
到只剩 spec 声明过的那几个名字;``pet_aes.HostedAgentService`` 则是调用方
(本模块自己的 ``run_agent``、CLI、未来的 HTTP 监听服务)应该打交道的"运行
边界",而不是自己去调 ``agent.run()`` —— 这正是让"CLI 应当通过 AES 进行通
信,而不是自己直接创建或运行该 agent"(ONBOARDING.md 原文)在代码里成立,
而不只是写在文档里的原因。

=== 补充说明(整体导读)===
把这几个文件串起来看:cli.py 只找 pet-aes 的 HostedAgentService 说话;
HostedAgentService 里面包着一个 pydantic_ai.Agent;这个 Agent 具体
"该怎么配"就是本文件负责的——包括:该用哪个大模型(create_llm)、
该有什么"性格/规则"(system.md 提示词)、能碰哪几个 MCP 工具
(PETSTORE_AGENT_SPEC 里的白名单),以及怎么把 pet-mcp 当子进程启动起来
(build_pet_mcp_toolset)。
"""

# os 标准库,用来读取/合并环境变量。
import os
# pathlib 标准库,Path 是"文件路径"的面向对象表示,比手写字符串拼路径更
# 安全、跨平台(自动处理 Windows 的反斜杠和 Linux 的正斜杠差异)。
from pathlib import Path

# Imported from fastmcp directly, not via pydantic_ai.mcp's re-export of it -
# mypy --strict flags that re-export as not "explicit" (no __all__ entry), the
# same implicit-reexport rule pet-mcp's own tests already had to work around.
# 直接从 fastmcp 导入,而不是通过 pydantic_ai.mcp 对它的转导出——mypy --strict
# 会把那个转导出标记为"不是显式导出"(没有 __all__ 条目),这跟 pet-mcp 自己的
# 测试之前已经遇到过、需要绕开的同一条规则。
# StdioTransport:fastmcp 库提供的类,表示"通过标准输入输出跟一个 MCP 服务器
# 子进程通信"的具体方式(下面会用它来真正启动 pet-mcp)。
from fastmcp.client.transports import StdioTransport
# 从 pet_aes 这个项目导入 AgentSpec(agent 的"规格说明"数据结构)和
# HostedAgentService(上一个文件读过的、真正托管运行 agent 的类)。
from pet_aes import AgentSpec, HostedAgentService
# 从 pet_aes 导入它的 build_agent 函数,但用 "as build_hosted_agent" 起了
# 一个本地别名——这是因为本文件自己下面也要定义一个叫 build_agent 的函数,
# 如果不改名字就会互相覆盖冲突,所以导入进来的这个用改过的名字引用。
from pet_aes import build_agent as build_hosted_agent
# pydantic_ai 库的 Agent 类,这里主要是用来做函数返回类型的类型注解。
from pydantic_ai import Agent
# pydantic_ai 库里对 MCP(Model Context Protocol)的支持,MCPToolset 表示
# "一整套从某个 MCP 服务器拿到的工具"。
from pydantic_ai.mcp import MCPToolset
# pydantic_ai 库的 Model 类型——表示"一个具体配置好的大语言模型"的抽象类型
# (不关心具体是哪个模型提供商,只要符合这个接口)。
from pydantic_ai.models import Model

# 从本项目自己的 config.py 导入 Settings(配置的数据结构)和
# get_settings(读取配置的函数)。
from pet_agent.config import Settings, get_settings
# 从本项目自己的 llm/client.py 导入 create_llm——负责"根据配置,真正构造出
# 一个可用的 Model 对象"这件事。
from pet_agent.llm.client import create_llm

# A generous but finite ceiling on how many model/tool round trips one customer
# message may take, so a confused model cannot loop forever instead of
# answering. Passed to HostedAgentService as its request_limit, which turns it
# into a UsageLimits(request_limit=...) on every call.
# 给一次顾客消息设置一个宽松但有限的"模型-工具往返"次数上限,这样即便模型犯了
# 糊涂,也不会无限循环下去而不给出答复。传给 HostedAgentService 的
# request_limit,它会在每次调用时把这个值变成一个
# UsageLimits(request_limit=...)。
# MAX_REQUESTS_PER_RUN:模块级常量(全大写命名),值是 10。
MAX_REQUESTS_PER_RUN = 10

# Where pet_agent.llm.prompts already keeps system.md - reused here rather
# than duplicated, so there is exactly one copy of the prompt file on disk.
# pet_agent.llm.prompts 已经在管理 system.md 这个文件了 —— 这里复用同一个
# 路径,而不是再复制一份,这样磁盘上就只有一份提示词文件。
# _PROMPTS_DIR:用下划线开头,表示这是模块内部使用的变量。
# Path(__file__):__file__ 是 Python 内置变量,值是"当前这个源代码文件自己
# 的路径";Path(__file__) 把它包装成一个 Path 对象。
# .parent:取这个文件所在的目录(比如文件是 .../pet_agent/agent.py,
# .parent 就是 .../pet_agent/ 这个目录)。
# " / "llm" / "prompts""":Path 对象重载了除号 / 运算符,用来拼接路径的
# 各级子目录/文件名——这是 pathlib 特有的、比字符串拼接更安全的写法,
# 最终结果相当于 .../pet_agent/llm/prompts 这个目录。
_PROMPTS_DIR = Path(__file__).parent / "llm" / "prompts"

# The Petstore assistant's spec: its prompt, and the only pet-mcp tools it may
# ever reach. Declared ``optional_tools`` rather than ``tools`` because these
# come from an MCP server that may be unreachable at startup - the same
# reason pet_aes.AgentSpec documents for that field.
#
# SECURITY: this tuple is the actual allow-list. pet_aes.build_agent filters
# the pet-mcp toolset down to exactly these three names, so the agent can
# never acquire a tool merely because pet-mcp happens to expose more of them
# later.
#
# Petstore 助手的 spec:它的提示词,以及它能碰到的、仅有的这几个 pet-mcp 工
# 具。声明成 ``optional_tools`` 而不是 ``tools``,是因为它们来自一个在启动时
# 可能连不上的 MCP 服务器 —— 跟 pet_aes.AgentSpec 给这个字段写的文档是同一个
# 原因。
#
# 安全边界:这个元组就是真正的白名单。pet_aes.build_agent 会把 pet-mcp 的
# toolset 过滤到只剩这三个名字,所以即便 pet-mcp 以后暴露了更多工具,这个
# agent 也绝不会因此顺带获得它们。
# PETSTORE_AGENT_SPEC:整个 agent 的"规格说明书",用 AgentSpec 这个数据类
# 构造出来。这是整个文件里定义的最重要的一个常量。
PETSTORE_AGENT_SPEC = AgentSpec(
    # name:这个 agent 的名字标识,方便日志/调试时区分。
    name="petstore-agent",
    # prompt_path:这个 agent 该用的"系统提示词"文件路径——上面拼好的
    # _PROMPTS_DIR 目录下的 system.md 文件,这个文件里写的就是"你是一个
    # Petstore 购物助手,应该怎么表现"这类指令。
    prompt_path=_PROMPTS_DIR / "system.md",
    # optional_tools:一个元组(小括号包起来、逗号分隔的固定序列,元组
    # 一旦创建就不能修改内容,比列表更适合表达"这是一份不该被意外改动的
    # 白名单")——列出这个 agent 唯一被允许使用的三个 pet-mcp 工具名字。
    # 这三个字符串必须跟 pet-mcp/server.py 里 @mcp.tool 装饰的函数名
    # 完全一致,才能真正被匹配上。
    optional_tools=(
        "pet_mcp_search_pets",
        "pet_mcp_get_pet",
        "pet_mcp_purchase_pet",
    ),
    # description:给这个 agent 的一句话描述,主要用于文档/日志展示。
    description="Conversational Petstore shopping assistant: helps a customer browse, filter, and buy pets.",
)


# build_pet_mcp_toolset:负责"把 pet-mcp 服务器启动起来,包装成一个
# MCPToolset 对象"这件事。
# settings: Settings:调用方传入的配置对象(下面会看到它包含
# petstore_api_base_url、pet_mcp_project_dir 等字段)。
def build_pet_mcp_toolset(settings: Settings) -> MCPToolset:
    """Build the toolset that launches pet-mcp as a stdio subprocess.

    构建一个工具集(toolset),把 pet-mcp 当作 stdio 子进程启动。

    ``uv run --project <dir> pet-mcp`` is exactly the command pet-mcp's own
    README documents (``make run``); ``PET_MCP_PROJECT_DIR`` only points
    ``--project`` at wherever this deployment's pet-mcp checkout lives, so the
    two projects can be side-by-side checkouts in local dev today and moved
    independently later without any code change here.
    这里用的 ``uv run --project <dir> pet-mcp`` 跟 pet-mcp 自己 README 里写的
    运行方式(``make run``)完全一样;``PET_MCP_PROJECT_DIR`` 只是指明这次部署
    里 pet-mcp 代码检出在哪个目录,这样今天两个项目可以在本地作为并排的目录
    存在,以后各自搬家也不需要改这里的代码。
    """
    # The subprocess needs PATH to find `uv` (and whatever `uv` itself needs
    # to run), plus the one Petstore-specific variable pet-mcp reads. MCP's
    # stdio transport would otherwise only inherit a tiny, fixed "safe" subset
    # of variables (PATH/HOME/...), which is not reliable enough across every
    # OS (notably Windows), so the full parent environment is passed through
    # explicitly instead.
    # 子进程需要 PATH 才能找到 `uv`(以及 `uv` 自己运行时需要的东西),再加上
    # pet-mcp 会读取的那一个 Petstore 专用变量。MCP 自带的 stdio 传输默认只会
    # 继承一个很小、固定的"安全变量"子集(PATH/HOME/……),这在不同操作系统上
    # (尤其是 Windows)并不总够用,所以这里显式地把父进程的完整环境透传过去。
    # "{**os.environ, "PETSTORE_API_BASE_URL": ...}":字典的"解包合并"写法
    # ——先把 os.environ(当前进程完整的环境变量,是一个类字典对象)里所有
    # 键值对铺开,再额外加一个/覆盖一个键 PETSTORE_API_BASE_URL,合并成一个
    # 新字典。如果 os.environ 里本来就有 PETSTORE_API_BASE_URL 这个键,
    # 后面写的这个会覆盖它(因为在字典字面量里,后出现的键值对会覆盖前面的)。
    env = {**os.environ, "PETSTORE_API_BASE_URL": settings.petstore_api_base_url}
    # StdioTransport(...):构造一个"通过标准输入输出通信的传输方式"对象,
    # 描述了具体要执行的命令。
    transport = StdioTransport(
        # command="uv":要执行的可执行文件名字。
        command="uv",
        # args=[...]:命令行参数列表,拼起来就是
        # "uv run --project <settings.pet_mcp_project_dir> pet-mcp"——
        # 也就是"用 uv 这个包管理器,在 pet-mcp 那个项目目录下,运行它的
        # pet-mcp 这个命令行入口"(对应 pet-mcp/pyproject.toml 里定义的
        # 命令行脚本,最终会执行 server.py 的 main() 函数)。
        args=["run", "--project", settings.pet_mcp_project_dir, "pet-mcp"],
        # env=env:把上面合并好的完整环境变量,传给这个即将启动的子进程。
        env=env,
    )
    # MCPToolset(transport):用这个传输方式,构造出一个 MCPToolset 对象
    # 返回——这个对象代表"一整套即将从 pet-mcp 这个子进程里拿到的工具",
    # 但真正的"启动子进程、建立连接"这个动作,发生在后面 agent 真正开始
    # 运行(即 HostedAgentService 的 __aenter__ 被调用)的时候,而不是这
    # 一行代码本身。
    return MCPToolset(transport)


# build_agent:负责"把 PETSTORE_AGENT_SPEC 这份规格说明 + 一个具体的模型 +
# 一个具体的工具集,组装成一个真正的 pydantic_ai.Agent 对象"。
# model: Model:上面导入的 Model 类型,表示已经配置好、可以直接使用的
# 大语言模型。
# toolset: MCPToolset:上面 build_pet_mcp_toolset 构造出来的那个工具集。
# 返回类型 Agent[None, str]:pydantic_ai 的 Agent 泛型——第一个类型参数
# None 表示"这个 agent 不需要任何额外的依赖对象注入",第二个 str 表示
# "它的最终输出永远是一段纯文本"。
def build_agent(model: Model, toolset: MCPToolset) -> Agent[None, str]:
    """Build the Petstore agent from ``PETSTORE_AGENT_SPEC`` via pet_aes.

    通过 pet_aes,从 ``PETSTORE_AGENT_SPEC`` 构建出 Petstore agent。

    This module never calls ``pydantic_ai.Agent(...)`` itself any more -
    ``pet_aes.build_agent`` is the one place that does, and it is also the
    place that filters ``toolset`` down to the three tool names
    ``PETSTORE_AGENT_SPEC`` declares. ``toolset`` is passed in rather than
    built here so tests can substitute an in-process fake MCP server for the
    real pet-mcp subprocess - see ``tests/test_agent.py``.
    这个模块自己不再调用 ``pydantic_ai.Agent(...)`` 了 —— ``pet_aes.build_agent``
    才是唯一这样做的地方,它同时也是把 ``toolset`` 过滤到
    ``PETSTORE_AGENT_SPEC`` 声明的那三个工具名的地方。``toolset`` 是从外部传
    进来的,而不是在这里直接构建,这样测试时就可以用一个进程内的假 MCP 服务
    器替换掉真正的 pet-mcp 子进程 —— 见 ``tests/test_agent.py``。
    """
    # build_hosted_agent(...):这就是前面用别名导入的 pet_aes.build_agent
    # (为了避免跟本函数自己重名,导入时改叫了 build_hosted_agent)。
    return build_hosted_agent(
        # 第一个位置参数:传入上面定义好的规格说明 PETSTORE_AGENT_SPEC。
        PETSTORE_AGENT_SPEC,
        # model=model:告诉 pet_aes 这个 agent 应该用哪个具体的大模型。
        model=model,
        # tools={}:一个空字典,表示"这个 agent 没有任何本地
        # (直接写在 Python 代码里的 @agent.tool)工具"——正如模块顶部
        # 文档说的,所有能力都必须来自 MCP,不允许有绕开 MCP 的本地工具。
        tools={},
        # toolsets=[toolset]:把上面构造好的 MCP 工具集,放进一个只有
        # 一个元素的列表里传进去(pet_aes.build_agent 支持同时挂多个
        # 工具集,这里这个 agent 只用到 pet-mcp 这一个)。
        toolsets=[toolset],
        # retries=2:如果模型调用工具时传的参数格式不对等可恢复的小错误,
        # 允许模型最多重试 2 次,而不是第一次出错就直接放弃。
        retries=2,
    )


# build_hosted_service:把"构建 agent"和"把它包进 HostedAgentService"这
# 两步合并成一个函数,是外部代码真正应该调用的入口。
def build_hosted_service(model: Model, toolset: MCPToolset) -> HostedAgentService:
    """Build the agent and hand it to a fresh ``HostedAgentService``.

    构建 agent,并把它交给一个全新的 ``HostedAgentService``。

    This is the one place a caller should get a running Petstore agent from -
    the CLI, ``run_agent`` below, and the future AES-hosted HTTP listener all
    call this rather than ``build_agent`` directly, so nothing outside
    ``pet_aes`` ever calls ``agent.run()`` or handles a raised model/tool
    exception itself.
    这是调用方获取一个可运行的 Petstore agent 的唯一入口 —— CLI、下面的
    ``run_agent``、以及未来 AES 托管的 HTTP 监听服务,都应该调用这个函数,而
    不是直接调用 ``build_agent``,这样 ``pet_aes`` 之外就没有任何代码会自己
    调用 ``agent.run()`` 或者自己处理被抛出的模型/工具异常。
    """
    # 先调用上面定义的 build_agent,拿到一个真正配置好的 Agent 对象。
    agent = build_agent(model, toolset)
    # 用这个 agent 构造一个新的 HostedAgentService,并且把上面定义的
    # MAX_REQUESTS_PER_RUN 常量,作为 request_limit 参数传进去——这样每一次
    # handle_message() 调用,都会受到这个次数上限的保护。
    return HostedAgentService(agent, request_limit=MAX_REQUESTS_PER_RUN)


# run_agent:一个更简单的、"一次性问答"用的辅助函数——本身是 async def
# (异步函数),调用它必须用 await。
async def run_agent(question: str) -> str:
    """Answer a single, standalone question - no memory of any other turn.

    回答单独的一句话 —— 不记忆任何其他轮次。

    Kept for simple one-shot callers (today's CLI asks exactly one question
    and exits); anything that needs to remember a real, multi-turn
    conversation should build its own ``HostedAgentService`` via
    :func:`build_hosted_service` and call ``handle_message()`` with the same
    ``session_id`` across turns instead (the future AES-hosted service and an
    interactive CLI both will).
    保留给简单的"一次性"调用方(今天的 CLI 就是问一句话然后退出);任何需要在
    真实的多轮对话里保留记忆的场景,都应该改为通过 :func:`build_hosted_service`
    构建自己的 ``HostedAgentService``,并在多轮之间用同一个 ``session_id`` 调
    用 ``handle_message()``(未来 AES 托管的服务和交互式 CLI 都会是这种场景)。
    """
    # 读取当前的配置(从环境变量/`.env` 文件等来源汇总而成的 Settings 对象)。
    settings = get_settings()
    # 根据配置,真正构造出一个可用的大模型对象——如果配置不完整/不合法,
    # create_llm 会返回 None,而不是直接抛异常。
    model = create_llm(settings)
    # 如果没能成功构造出模型(比如没配置 LLM_BACKEND 或密钥缺失),
    # 就主动抛出一个运行时错误,提前、明确地失败,而不是继续往下跑到某个
    # 更难定位问题的地方才崩溃。
    if model is None:
        raise RuntimeError("LLM not configured; set LLM_BACKEND and credentials")
    # 构造 MCP 工具集(会真正准备好"待会儿要怎么启动 pet-mcp 子进程"这件事,
    # 但此时还没真的启动)。
    toolset = build_pet_mcp_toolset(settings)
    # "async with build_hosted_service(...) as service:"——构造好
    # HostedAgentService 后,用异步上下文管理器的方式使用它:进入时才真正
    # 建立 MCP 连接(启动 pet-mcp 子进程),离开这个代码块时自动清理干净。
    async with build_hosted_service(model, toolset) as service:
        # 调用 handle_message,把这一句独立的问题交给 agent 处理,并把它的
        # 回复原样返回给调用方。因为没有传 session_id,这里用的是
        # HostedAgentService 里 session_id 参数的默认值 "default"。
        return await service.handle_message(question)
