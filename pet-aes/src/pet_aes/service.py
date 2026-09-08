"""The operational boundary that hosts a running agent.

Per ONBOARDING.md section 12, step 7, AES should: receive a customer message,
run the Pydantic AI agent, provide an already-configured connection to the
MCP server, return the final response, and follow the organization's
conventions for lifecycle management, logging and error handling. Everything
else in this package (:mod:`pet_aes.agents`) is about *building* an agent;
this module is about *running* one, safely, for as long as a conversation
lasts.

A caller (a CLI, a future HTTP listener, anything) builds the agent once via
:func:`pet_aes.agents.build_agent` — MCP toolset(s) already attached and
already filtered to the spec's allow-list — hands it to
:class:`HostedAgentService`, and from then on talks only to the service:
``handle_message()`` in, a reply out. It never calls ``agent.run()`` itself
and never sees a raised tool/model exception; that is what "the CLI talks to
AES, not to the agent" (ONBOARDING.md's own wording) means in code.

本模块是承载一个正在运行的 agent 的"运行边界"。

按 ONBOARDING.md 第 12 节第 7 步的说法,AES 应该:接收顾客的消息、运行
Pydantic AI agent、提供一个已经配置好的、连接到 MCP 服务器的连接、返回最终
响应,并且遵循组织在生命周期管理、日志记录和错误处理上的约定。这个包里的
另一个模块(:mod:`pet_aes.agents`)负责的是"怎么构建"一个 agent;这个模块
负责的是"怎么运行"它——在整场对话持续期间,安全地运行。

调用方(一个 CLI、未来的一个 HTTP 监听服务、任何东西)通过
:func:`pet_aes.agents.build_agent` 把 agent 构建好一次——MCP toolset 已经接
好、也已经按 spec 的白名单过滤过了——把它交给 :class:`HostedAgentService`,
从那以后就只跟这个 service 打交道:调一次 ``handle_message()``,拿到一句
回复。调用方自己从来不调用 ``agent.run()``,也从来看不到一个被抛出的
tool/model 异常——这正是"CLI 应当通过 AES 进行通信,而不是自己直接创建或
运行该 agent"(ONBOARDING.md 原文)在代码里的样子。

=== 补充说明(整体导读)===
如果说 pet-mcp 的 server.py 是"顾客能买什么"的边界,那这个文件就是
"顾客怎么跟 agent 说话"的边界。CLI(cli.py)从头到尾只认识这个文件里的
HostedAgentService 这一个类:把用户打的字丢进 handle_message(),拿到
一句回复字符串——至于 agent 内部怎么调用大语言模型、怎么调用 MCP 工具、
出了错怎么办,CLI 完全不需要知道,也不允许直接接触。这正是
"关注点分离"(separation of concerns)的一个典型例子。
"""

# logging 是 Python 标准库,提供"记日志"的能力——出错时把详细信息写到
# 服务器自己的日志里,而不是把细节暴露给最终用户。
import logging
# typing 标准库,Any 表示"任意类型"——下面 Agent[Any, str] 用到,
# 表示"这个 Agent 的依赖类型可以是任意的,但它的输出类型固定是 str
# (字符串)"。
from typing import Any

# pydantic_ai 是本项目使用的、用来构建"AI agent"的第三方库。
# Agent:这个库里最核心的类,代表"一个配置好的、可以对话的智能体"
# (绑定了具体用哪个大模型、可以用哪些工具等)。
from pydantic_ai import Agent
# ModelMessage:pydantic_ai 定义的"一条对话消息"的类型(可能是用户说的话、
# 模型的回复、工具调用记录等)——下面用来给"对话历史"这个概念做类型注解。
from pydantic_ai.messages import ModelMessage
# UsageLimits:pydantic_ai 提供的"用量限制"配置,可以限制一次 agent.run()
# 调用里最多能发起多少次请求(比如防止模型在一次回复里无限循环调用工具)。
from pydantic_ai.usage import UsageLimits

# DEFAULT_FALLBACK_MESSAGE:一个模块级别的常量字符串——当 agent 运行出错时,
# 默认用这句话回复顾客,而不是把真实的错误信息或者堆栈泄露出去。
# 全大写命名(DEFAULT_FALLBACK_MESSAGE)是 Python 里"这是一个常量,不应该
# 被随便改动"的约定俗成写法。
DEFAULT_FALLBACK_MESSAGE = "Sorry, something went wrong on our end - please try again in a moment."

# logger:给这个模块单独创建一个日志记录器。
# logging.getLogger(__name__):__name__ 是 Python 内置变量,值是当前模块的
# 名字(比如 "pet_aes.service")——用模块名当作 logger 的名字,是 Python
# 日志系统的标准做法,这样以后如果日志里看到某条记录是从这个 logger 打出来的,
# 就能一眼看出是这个文件产生的。
logger = logging.getLogger(__name__)


# HostedAgentService:整个文件的核心类,"AES 托管一个 agent"这句话
# 具体来说就是"用这个类的一个实例包住一个 Agent"。
class HostedAgentService:
    """Owns one agent's lifecycle and every conversation running through it.

    拥有一个 agent 的完整生命周期,以及所有正在通过它进行的对话。

    Use as an async context manager so the agent's toolsets (the MCP
    connection among them) are entered once, for the lifetime of the service,
    instead of once per message - reusing the connection is exactly "提供
    已经配置好的、连接到 MCP 服务器的连接" (ONBOARDING.md section 12, step 7)
    rather than reconnecting on every turn::

        async with HostedAgentService(agent) as service:
            reply = await service.handle_message("do you have any cats?", session_id="alice")
            reply = await service.handle_message("tell me about the first one", session_id="alice")

    One service can hold many independent conversations at once, keyed by
    ``session_id`` - each customer's history stays separate from every other
    customer's.
    一个 service 可以同时持有多场互不相干的对话,用 ``session_id`` 区分——每
    个顾客的历史记录都跟其他顾客的分开保存。
    """

    # __init__:构造函数。
    def __init__(
        self,
        # agent:调用方事先构建好的 Agent 实例(在 pet-agent 项目里,是
        # agent.py 的 build_agent 函数构造出来的那个,已经接好 MCP 工具、
        # 配好用哪个大模型)。
        # 类型注解 Agent[Any, str]:pydantic_ai 的 Agent 是一个"泛型类",
        # 方括号里第一个类型参数是"依赖类型"(这里不关心,写 Any 表示任意),
        # 第二个是"输出类型"(这里固定是 str,表示这个 agent 的回复永远是
        # 一段纯文本,不是结构化数据)。
        agent: Agent[Any, str],
        *,
        # service_logger:允许调用方传入自己的 logger 实例,不传就用上面
        # 模块级别创建的默认 logger。
        service_logger: logging.Logger | None = None,
        # fallback_message:出错时的兜底回复文案,默认用上面定义的常量。
        fallback_message: str = DEFAULT_FALLBACK_MESSAGE,
        # request_limit:限制一次对话轮次里,agent 最多能发起多少次请求
        # (调用模型/调用工具的总次数),默认给 10——防止出现异常情况下的
        # 无限循环调用。设成 None 就表示不限制。
        request_limit: int | None = 10,
    ) -> None:
        # 把传进来的 agent 存成实例属性,后面所有方法都通过 self._agent
        # 使用它。
        self._agent = agent
        # Named parameter avoids shadowing the module-level `logging` import
        # and lets a caller inject its own logger (e.g. one with extra
        # context bound) without this class knowing anything about how
        # logging was configured - it just uses whatever it is given.
        # 参数名避开跟模块级 `logging` 的重名,也让调用方可以注入自己的
        # logger(比如一个已经绑好额外上下文的)——这个类完全不需要知道日志是
        # 怎么配置的,给它什么就用什么。
        # "service_logger or logger":如果调用方传了自己的 logger(不是
        # None),就用它;否则用模块级别的默认 logger 兜底——这是 Python
        # 里常见的"用 or 做默认值兜底"的写法。
        self._logger = service_logger or logger
        # 存下兜底回复文案。
        self._fallback_message = fallback_message
        # 存下用量限制的数值。
        self._request_limit = request_limit
        # self._histories:一个字典,用来存"每个 session 的对话历史"。
        # 类型注解 dict[str, list[ModelMessage]]:键是字符串(session_id),
        # 值是"ModelMessage 对象组成的列表"(这场对话到目前为止的完整消息
        # 记录)。初始化成空字典,表示服务刚启动时还没有任何对话历史。
        self._histories: dict[str, list[ModelMessage]] = {}

    # __aenter__:配合 "async with HostedAgentService(...) as service:"
    # 用法的进入方法。
    async def __aenter__(self) -> HostedAgentService:
        # 调用底层 agent 自己的 __aenter__——pydantic_ai 的 Agent 本身也是
        # 一个异步上下文管理器,它的"进入"动作会真正建立好 MCP 工具连接
        # (比如把 pet-mcp 当子进程启动、建立 stdio 管道)。这里等于是把
        # "进入"这个动作,从 HostedAgentService 转发给它内部持有的 agent。
        await self._agent.__aenter__()
        # 返回自身,让 "as service" 拿到的就是这个 HostedAgentService 实例。
        return self

    # __aexit__:配套的"退出"方法。
    # "*exc_info: object":用 * 收集所有位置参数(异常类型、异常对象、
    # traceback 这三个,Python 异步上下文管理器协议规定的固定参数),
    # 类型注解成 object(最宽泛的类型),因为这里不关心具体内容,只是原样
    # 转发。
    async def __aexit__(self, *exc_info: object) -> None:
        # 把这三个参数原样转发给底层 agent 自己的 __aexit__,让它负责真正
        # 关闭 MCP 连接、清理子进程等收尾工作。
        # "*exc_info":在函数调用时,给一个收集起来的元组前面加星号,
        # 表示"把这个元组拆开,当作多个独立的位置参数传进去"——是
        # "收集参数"(在参数定义处)的逆操作("展开参数",在调用处)。
        await self._agent.__aexit__(*exc_info)

    # handle_message:整个类里最重要的方法——所有对话都通过它进行。
    # message: str:顾客这一轮说的话。
    # session_id: str = "default":这轮对话属于哪个会话,不传就用
    # "default" 这个默认会话。
    # 返回类型 str:agent 的回复文本。
    async def handle_message(self, message: str, *, session_id: str = "default") -> str:
        """Receive one customer message, run the agent, return its reply.

        接收顾客的一句话,运行 agent,返回它的回复。

        Every session's own history is threaded through automatically -
        callers never handle ``ModelMessage`` objects themselves. Any
        exception raised while running the agent (a broken model connection,
        an MCP tool call that failed in a way the model itself could not
        recover from, anything else) is logged with a full traceback
        server-side and replaced with ``fallback_message`` here - the
        customer never sees a raw exception, a stack trace, or any detail
        that could leak an internal error or a secret.
        每个 session 自己的历史记录都会被自动串起来——调用方自己完全不用碰
        ``ModelMessage`` 这些对象。运行 agent 时抛出的任何异常(模型连接
        断了、一次 MCP 工具调用以模型自己没法恢复的方式失败了、或者别的什么
        情况)都会在这里被完整记录到日志里(服务器这一侧),然后换成
        ``fallback_message`` 返回——顾客永远看不到一个裸露的异常、一段
        堆栈,或者任何可能泄露内部错误或密钥的细节。
        """
        # 从 self._histories 字典里,按 session_id 取出这个会话到目前为止
        # 的历史消息列表;如果这个 session_id 是第一次出现(字典里还没有
        # 对应的键),.get(session_id, []) 会返回一个空列表兜底——表示
        # "这是一场全新的对话,还没有任何历史"。
        history = self._histories.get(session_id, [])
        # 根据 self._request_limit 是否设置(不是 None/0 这种"假值"),
        # 构造一个 UsageLimits 对象来限制这一次调用最多能发起多少请求;
        # 如果 self._request_limit 本身是 None,usage_limits 就是 None,
        # 表示不设限制。这是一个"条件表达式"(三元写法)。
        usage_limits = UsageLimits(request_limit=self._request_limit) if self._request_limit else None
        # try/except:把真正运行 agent 的这一步整个包起来——这是"顾客
        # 永远不会看到裸露的异常"这条承诺的具体实现位置。
        try:
            # self._agent.run(...):pydantic_ai 的 Agent 提供的核心方法,
            # 真正驱动一整轮"跟大模型对话、模型决定要不要调用工具、执行
            # 工具、把结果再喂回模型、直到模型给出最终文字回复"的完整流程。
            #   message —— 这一轮顾客说的话
            #   message_history=history —— 把之前的历史消息一起喂给模型,
            #     让模型知道"之前聊了什么"(这就是"follow-up reference"
            #     这类场景,比如"第一个""它"能被正确理解的原因)
            #   usage_limits=usage_limits —— 传入上面构造好的用量限制
            result = await self._agent.run(message, message_history=history, usage_limits=usage_limits)
        # except Exception:捕获*所有*类型的异常(Exception 是几乎所有
        # 常规异常的公共基类)——不管是模型连接失败、工具调用出错,还是
        # 别的什么没预料到的情况,统一在这里兜底处理,不让任何异常真正
        # 冒泡到调用这个方法的 CLI 代码里去。
        except Exception:
            # self._logger.exception(...):专门用来在 except 块里记录日志
            # 的方法——它会自动把"当前正在处理的这个异常"的完整堆栈信息
            # 也一起写进日志(不需要手动传异常对象)。
            # "%r" 是 Python 旧式字符串格式化里的"repr 格式"占位符,
            # 会把 session_id 用 repr() 的形式打印出来(比如加上引号),
            # 方便在日志里清楚地看出这是个字符串、边界在哪。
            self._logger.exception("Agent run failed for session %r", session_id)
            # 不把异常继续往外抛,而是直接返回预设的兜底回复文案——
            # 这样调用这个方法的 CLI 永远只会拿到一个正常的字符串,不会
            # 意外崩溃,也不会看到内部错误细节。
            return self._fallback_message
        # 走到这里说明 agent.run() 顺利跑完了(没有抛异常)。
        # result.all_messages():从这次运行结果里,取出"这一轮补充了新消息
        # 之后的完整历史"(包含之前的历史加上这一轮新产生的消息),覆盖存回
        # self._histories 字典里对应 session_id 的位置——这样下一次同一个
        # session_id 再调用 handle_message 时,就能接着这段历史继续对话。
        self._histories[session_id] = result.all_messages()
        # result.output:这次运行的最终文字回复(前面 Agent[Any, str] 的
        # 第二个类型参数 str,说的就是这里的类型),返回给调用方(CLI)。
        return result.output

    # forget:提供一个"清空某个会话历史"的能力,比如顾客说"我们重新开始
    # 吧",CLI 就可以调这个方法。
    def forget(self, session_id: str = "default") -> None:
        """Drop one session's history, e.g. when a customer starts over.

        丢掉某一个 session 的历史记录,比如顾客说"我们重新开始吧"的时候。
        """
        # dict.pop(key, None):从字典里删除指定的键,如果这个键原本就不
        # 存在,就返回 None 而不是报错(第二个参数是"找不到时的默认返回值",
        # 这里没有用到这个返回值,只是借用这个写法来"安全地删除,不管
        # 原来存不存在都不报错")。
        self._histories.pop(session_id, None)

    # active_sessions:查询当前这个 service 手里还留着历史记录的所有
    # session_id 有哪些——主要用于调试/观测,不是顾客对话流程本身需要的。
    def active_sessions(self) -> list[str]:
        """The session ids this service currently holds history for."""
        # list(self._histories):对一个字典直接调用 list(...),取出的是
        # 这个字典所有的"键"组成的列表(等价于 list(self._histories.keys()),
        # 只是更简洁的写法)。
        return list(self._histories)


# __all__:Python 的模块级约定变量——声明"当别的代码写
# 'from pet_aes.service import *' 时,应该导入哪些名字"。这里显式列出
# DEFAULT_FALLBACK_MESSAGE 和 HostedAgentService 这两个,表示它们是这个
# 模块真正想对外公开的部分,其他模块内部用到的东西(比如 logger)不会被
# 这种"星号导入"带出去。
__all__ = ["DEFAULT_FALLBACK_MESSAGE", "HostedAgentService"]
