"""Console entrypoint: an interactive command-line dialogue with the Petstore assistant.

Per ONBOARDING.md section 12, step 8, this module is the "small Petstore
employee" the customer actually talks to: it welcomes them, explains what it
can do, loops accepting free-text messages, and lets them continue browsing
or leave. It does not decide anything about pets, prices, availability, or
purchases itself - every one of those decisions is the agent's, reached
through :func:`pet_agent.agent.build_hosted_service` (a
``pet_aes.HostedAgentService``). This module never builds or calls a
``pydantic_ai.Agent`` directly and never imports ``pet_mcp``, ``pet_client``,
or a database driver - "CLI 应当通过 AES 进行通信,而不是自己直接创建或运行
该 agent" (ONBOARDING.md's own wording) is true here in the same way it is in
``agent.py``.

Only the assistant's own reply text is ever printed - no tool call/result
details, no raw model output, no validation traces, no API response bodies,
and no secrets, matching ONBOARDING.md section 12, step 8's explicit list of
what a customer must never see. (``verify_agent_conversation.py``, in
contrast, is a diagnostic script for the developer and deliberately does
print that internal detail - this module is the actual customer experience
and does not.)

按 ONBOARDING.md 第 12 节第 8 步,本模块就是顾客真正对话的那个"小小的宠物店
店员":欢迎顾客、说明自己能做什么,循环接受自由文本消息,并且让顾客可以继续
逛下去或者离开。它自己完全不决定任何关于宠物、价格、库存或购买的事情——这些
决定全部属于 agent,通过 :func:`pet_agent.agent.build_hosted_service`
(一个 ``pet_aes.HostedAgentService``)去问 agent。本模块从来不直接构建或调用
``pydantic_ai.Agent``,也从来不 import ``pet_mcp``、``pet_client`` 或者数据库
驱动 —— "CLI 应当通过 AES 进行通信,而不是自己直接创建或运行该 agent"
(ONBOARDING.md 原文)在这里成立的方式,跟在 ``agent.py`` 里是一样的。

这里只打印 assistant 自己的回复文本——没有工具调用/返回结果的细节、没有原始
模型输出、没有校验过程、没有 API 响应体、也没有任何密钥,对应 ONBOARDING.md
第 12 节第 8 步明确列出的、顾客绝不应该看到的那几样东西。(相比之下,
``verify_agent_conversation.py`` 是给开发者看的诊断脚本,故意会打印那些内部
细节——本模块是真正的顾客体验,不会。)

=== 补充说明(整体导读)===
这是整个系统里,唯一一个"人真正打字进去"的地方。main() 负责"一次性的
准备工作"(读配置、配好日志、造好模型和 MCP 工具集、包成 service),
run_dialogue() 负责"真正的多轮对话循环"——两者分开,是因为
verify_agent_conversation.py 这类脚本也想复用同样的"准备工作"逻辑,
但用自己的对话脚本代替真人在终端上打字。
"""

# asyncio 是 Python 标准库,用来运行"异步程序"——整个项目大量用到
# async/await(网络请求、MCP 通信都是异步的),而普通脚本从"同步的
# main() 函数"启动,需要 asyncio.run(...) 这样一个入口把两者接起来。
import asyncio
# sys 标准库,这里用来往标准错误流(stderr)打印错误信息,以及
# raise SystemExit 时提供退出码。
import sys
# uuid 标准库,用来生成"全局唯一标识符"——下面用来给每一次对话/每一次
# 程序运行生成一个随机的、几乎不会重复的 id。
import uuid
# collections.abc 标准库,Callable 是"可调用对象"的类型注解(表示
# "任何函数,或者任何实现了 __call__ 的对象",不局限于普通函数)。
from collections.abc import Callable

# 从 pet_aes 导入 HostedAgentService,只是用来做类型注解
# (run_dialogue 的 service 参数)。
from pet_aes import HostedAgentService

# 从本项目自己的 agent.py 导入两个构建函数:
#   build_hosted_service —— 构建"agent + HostedAgentService"的组合
#   build_pet_mcp_toolset —— 构建 pet-mcp 的工具集
from pet_agent.agent import build_hosted_service, build_pet_mcp_toolset
# 从 config.py 导入 get_settings——读取整个程序的配置。
from pet_agent.config import get_settings
# 从 llm/client.py 导入 create_llm——根据配置构造出真正可用的模型对象。
from pet_agent.llm.client import create_llm
# 从 logging_config.py 导入两个跟日志相关的函数:
#   set_correlation_id —— 给这一整次程序运行打上一个统一的"关联 id",
#     方便以后在日志里把同一次运行产生的所有日志行串起来看
#   setup_logging —— 按配置初始化日志系统(格式、级别等)
from pet_agent.logging_config import set_correlation_id, setup_logging
# 从 observability.py 导入 setup_telemetry——初始化可观测性相关的设施
# (比如链路追踪、指标上报,如果配置了的话)。
from pet_agent.observability import setup_telemetry

# Step 8, items 1-2: a welcome message plus a plain explanation of what the
# customer can do, so nobody needs to already know how to "talk to an agent"
# to use this. Written once, here, rather than left to the model to explain
# on its own initiative - that would make the very first thing a customer
# sees depend on the model following an instruction rather than on
# deterministic CLI text.
# 对应第 8 步的第 1、2 项:一句欢迎语,加上一段用大白话写的"你能做什么"说
# 明,这样谁都不需要先学会"怎么跟一个 agent 对话"才能用这个程序。这段话写死
# 在这里,而不是指望模型自己主动去解释——那样的话,顾客看到的第一句话就要
# 依赖模型有没有听指令,而不是一段确定不变的 CLI 文本。
# WELCOME:模块级常量,是一个"三重引号字符串"(可以跨多行书写)。
# 字符串前面的反斜杠 \(紧跟在三个引号后面)是 Python 的"续行"写法,
# 表示"这里不要换行",让第一行内容("Welcome to the Petstore!")紧接在
# 引号后面,而不会在字符串开头多出一个空行。
WELCOME = """\
Welcome to the Petstore!

I can help you:
  - find a pet (just describe what you're looking for)
  - see more details about a pet you've asked about
  - buy a pet, once you've confirmed you want it

Type 'exit' or 'quit' any time you'd like to leave.
"""

# CLI-level commands, handled here rather than sent to the agent - the
# customer needs a definite way to end the process, and recognizing a
# literal word for that is a property of this dialogue shell, not a decision
# about Petstore data.
# 这几个词由 CLI 自己处理,不会发给 agent —— 顾客需要一个确定的办法结束这个
# 程序,而识别这么几个字面词汇,是这个"对话外壳"本身的行为,不是什么关于
# Petstore 数据的决定。
# _EXIT_WORDS:一个 frozenset(不可变集合)——用集合而不是列表,是因为
# 下面判断"用户输入的词是不是在这个集合里"这个操作,集合的查找速度是
# O(1)(几乎瞬间),比列表的"逐个比对"更快;用 frozenset(不可变版本)
# 而不是普通 set,是因为这是一个不应该被意外修改的常量。
_EXIT_WORDS = frozenset({"exit", "quit", "q", ":q", "bye", "goodbye"})


# run_dialogue:真正的对话循环所在的函数,是 async def(异步函数)。
async def run_dialogue(
    # service:一个已经构建好、且已经"进入"了异步上下文的 HostedAgentService
    # ——由调用方(下面的 main())负责构建和管理生命周期,这个函数本身
    # 不负责创建它。
    service: HostedAgentService,
    *,
    # session_id:这场对话的会话标识,不传就是 None,函数体内部会在
    # 这种情况下自动生成一个。
    session_id: str | None = None,
    # input_func:用来"读一行用户输入"的函数,类型注解
    # Callable[[str], str] 表示"一个函数,接收一个字符串参数(提示符文字),
    # 返回一个字符串(用户输入的内容)"。默认值直接就是 Python 内置的
    # input 函数本身——把函数当作"值"传递、赋给默认参数,这是 Python
    # 里"函数是一等公民"的体现。
    input_func: Callable[[str], str] = input,
    # print_func:同理,用来"打印一行输出"的函数,类型是
    # Callable[[str], None](接收一个字符串,不返回任何有意义的值),
    # 默认值是内置的 print 函数。
    print_func: Callable[[str], None] = print,
) -> None:
    """Hold the customer's dialogue: welcome, loop, continue-or-exit (Step 8, items 1-3, 9).

    跟顾客对话:欢迎、循环、继续或者离开(对应第 8 步第 1-3、9 项)。

    ``input_func``/``print_func`` default to the real builtins but can be
    substituted in tests with fakes that feed scripted input and record what
    was printed, without touching real stdin/stdout.
    ``input_func``/``print_func`` 默认是真正的内置函数,但测试时可以换成假
    的实现,喂入写好的输入、并记录打印过什么,而不需要真的碰 stdin/stdout。

    Showing pets, pet details, the purchase offer, the confirmation question,
    and the receipt or failure explanation (Step 8, items 4-8) all happen
    inside the single ``print_func(f"Petstore: {reply}")`` line below -
    those are the agent's own decisions, reached through ``service``, not
    something this loop formats or decides itself.
    展示宠物、宠物详情、购买提议、确认问题,以及收据或失败说明(第 8 步第
    4-8 项),全部发生在下面这一行 ``print_func(f"Petstore: {reply}")``
    里——那些是 agent 自己(通过 ``service``)做出的决定,不是这个循环自己
    格式化或者决定的。
    """
    # "session_id or f"cli-{...}"":如果调用方传了 session_id(非 None,
    # 也非空字符串这种"假值"),就用调用方传的;否则(常见情况——没传)
    # 自动生成一个形如 "cli-a1b2c3d4" 的新 id。
    # uuid.uuid4():生成一个随机的 UUID(通用唯一标识符)对象。
    # .hex:把这个 UUID 转换成一个 32 位的十六进制字符串(没有中划线)。
    # [:8]:切片操作,只取这个字符串的前 8 个字符——不需要完整的 32 位,
    # 只是想要一个"足够不容易撞车"的短标识,方便在日志里阅读。
    session_id = session_id or f"cli-{uuid.uuid4().hex[:8]}"
    # 打印欢迎语——用的是传进来的 print_func(默认是内置 print),而不是
    # 直接写死 print(...),这正是为了让测试可以替换掉它。
    print_func(WELCOME)
    # while True:一个"无限循环",只有内部显式 return 或者程序退出才会结束
    # ——这正是"持续对话,直到顾客选择离开"这件事在代码里的样子。
    while True:
        # try/except:把"读取用户输入"这一步包起来,因为用户可能用
        # Ctrl-D/Ctrl-C 这种方式,以异常的形式"提前结束输入",而不是正常
        # 打字后按回车。
        try:
            # input_func("You: ")——调用输入函数,"You: " 是显示给用户看的
            # 提示符;raw 存下用户实际输入的这一整行原始文本。
            raw = input_func("You: ")
        # 【这里是我发现并修正的一处真实的语法错误——原文件写的是
        # "except EOFError, KeyboardInterrupt:",这是 Python 2 的旧语法,
        # 在 Python 3 里会直接导致 SyntaxError(整个文件都没法被正常
        # 加载/编译)。Python 3 要求同时捕获多种异常类型时,必须用一个
        # 元组把它们括起来,写成 "except (EOFError, KeyboardInterrupt):"
        # ——下面这一行就是修正后的写法。】
        # EOFError:当输入流被"结束"时抛出(比如用户按了 Ctrl-D,或者在
        # Windows 上是 Ctrl-Z 加回车)。
        # KeyboardInterrupt:当用户按 Ctrl-C 强行打断程序时抛出。
        # 这里把两种情况一起捕获,因为不管是哪一种,都应该"体面地退出",
        # 而不是让程序崩溃、打印一段吓人的堆栈。
        except (EOFError, KeyboardInterrupt):
            # Ctrl-D/Ctrl-C (or, on Windows, Ctrl-Z+Enter) leaves just as
            # cleanly as typing an exit word - Step 8, item 9's "or exit"
            # should not require knowing the right word to type.
            # Ctrl-D/Ctrl-C(在 Windows 上是 Ctrl-Z+回车)离开的方式,应该跟打
            # 一个退出词一样干净——第 8 步第 9 项里的"或者离开",不应该非得先
            # 知道该打哪个词才行。
            # "\nGoodbye!":字符串开头的 "\n" 是换行符——因为用户刚才按
            # Ctrl-D/Ctrl-C 时,光标可能还停在 "You: " 这一行的末尾,先换一行
            # 再打印"再见",视觉上更整洁。
            print_func("\nGoodbye!")
            # return:直接结束这个函数(也就跳出了 while True 循环),
            # 对话到此为止。
            return
        # raw.strip():去掉用户输入首尾的空白字符(比如不小心多打的空格、
        # 回车)。
        message = raw.strip()
        # 如果去除空白后是空字符串(用户啥都没打,直接按了回车),
        # "continue" 跳过本次循环剩下的部分,直接回到 while 循环开头,
        # 重新打印提示符等待输入——不会把空消息发给 agent。
        if not message:
            continue
        # message.lower():把输入转成全小写,这样 "Exit"、"EXIT"、"exit"
        # 都能被识别成退出指令。
        # "in _EXIT_WORDS":检查这个小写字符串是否在上面定义的退出词集合里。
        if message.lower() in _EXIT_WORDS:
            print_func("Petstore: Thanks for stopping by - goodbye!")
            return
        # 走到这里,说明这是一句"正常的、需要交给 agent 处理"的消息——
        # await service.handle_message(...):调用 pet-aes 的
        # HostedAgentService,把这句话和当前的 session_id 一起交给它,
        # 等待 agent(经过大模型 + MCP 工具调用)得出最终的文字回复。
        reply = await service.handle_message(message, session_id=session_id)
        # 把 agent 的回复,加上 "Petstore: " 前缀,打印出来——注意这里
        # 打印的只有 reply 这一个字符串本身,不涉及任何工具调用细节、
        # 原始 HTTP 响应等内部信息,呼应了模块开头文档强调的"顾客只能看到
        # 助手自己的回复文本"这条规则。
        print_func(f"Petstore: {reply}")


# main:整个命令行程序真正的入口函数(是普通的同步函数,不是 async def
# ——它内部会自己去启动一个异步事件循环)。
def main() -> None:
    """Configure the process, build the AES-hosted service, run the dialogue.

    配置好这个进程,构建 AES 托管的 service,然后跑对话。

    Every piece the dialogue itself needs (the model, the pet-mcp toolset,
    and the ``HostedAgentService`` that wraps them) is built here, once, for
    the life of the whole conversation - the same startup shape
    ``verify_agent_conversation.py`` uses, and the reason ``run_dialogue``
    above only ever needs an already-built ``service`` and never touches
    ``Settings`` or ``create_llm`` itself.
    对话本身需要的每一样东西(模型、pet-mcp 的 toolset,以及包住它们的
    ``HostedAgentService``)都在这里构建一次,贯穿整场对话——
    跟 ``verify_agent_conversation.py`` 的启动方式是一样的,这也是为什么上面
    的 ``run_dialogue`` 只需要一个已经构建好的 ``service``,自己完全不碰
    ``Settings`` 或者 ``create_llm``。
    """
    # 读取配置(环境变量/`.env` 汇总成的 Settings 对象)。
    settings = get_settings()
    # 按配置里的日志级别/格式,初始化整个进程的日志系统。
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    # 按配置初始化可观测性设施(如果配置里开启了的话)。
    setup_telemetry(settings)
    # One id for the whole run, so every tool call and retry is traceable to it.
    # 给整场运行生成一个统一的"关联 id"(格式类似 "run-a1b2c3d4e5f6"),
    # 存进 logging 相关的上下文里——以后翻日志时,可以用这个 id 把"这一次
    # 程序运行"产生的所有日志行(不管来自哪个模块、哪次工具调用)都关联到
    # 一起,方便排查问题。
    set_correlation_id(f"run-{uuid.uuid4().hex[:12]}")

    # 根据配置构造真正的大模型对象。
    model = create_llm(settings)
    # 如果没能成功配置出模型:
    if model is None:
        # 直接把清晰的错误信息打印到标准错误流(stderr,不是普通的标准
        # 输出 stdout)——这是命令行程序的惯例,方便运维/开发者用工具区分
        # "正常输出"和"错误信息"。
        print("error: LLM not configured; set LLM_BACKEND and credentials", file=sys.stderr)
        # raise SystemExit(2):抛出 SystemExit 异常,这是 Python 里"让整个
        # 程序退出、并带上一个退出码"的标准方式——退出码 2 按惯例表示
        # "命令行参数/配置有问题"(0 表示成功,不同的非 0 数字通常有各自的
        # 惯例含义)。
        raise SystemExit(2)

    # 构造 pet-mcp 的工具集(还没真正启动子进程)。
    toolset = build_pet_mcp_toolset(settings)

    # _main:在 main() 函数内部,再定义一个嵌套的 async def 函数——
    # 因为 main() 本身是同步函数,不能直接写 await,所以把真正需要
    # "异步等待"的逻辑都收进这个内层函数里,稍后统一用 asyncio.run 驱动。
    async def _main() -> None:
        # try/except:把"构建 service、跑对话"这一整个过程包起来,专门
        # 处理"启动阶段就失败了"的情况(比如 pet-mcp 这个子进程根本起不来、
        # 或者提示词文件丢了)。
        try:
            # 构建 HostedAgentService,并用 async with 语法管理它的生命
            # 周期——进入时才真正启动 pet-mcp 子进程、建立 MCP 连接。
            async with build_hosted_service(model, toolset) as service:
                # 调用上面定义的 run_dialogue,把构建好的 service 交给它,
                # 真正开始跟用户的交互式对话循环。
                await run_dialogue(service)
        # except Exception as exc:捕获这个 try 块里发生的任何异常
        # (启动失败,或者 run_dialogue 内部意外冒出的、没被更内层处理掉的
        # 异常)。
        except Exception as exc:
            # A startup failure (pet-mcp would not launch, the prompt file is
            # missing, ...) is an operator-facing problem, not a customer-facing
            # chat turn - it gets one plain-English line, never a raw
            # traceback, matching the same never-expose-internals boundary
            # run_dialogue's own docstring describes.
            # 启动失败(pet-mcp 起不来、提示词文件不在了……)是运维层面的问题,
            # 不是顾客对话里的一轮——它只得到一行用大白话写的说明,绝不是一段
            # 裸露的堆栈跟踪,这跟 run_dialogue 自己文档里说的"绝不暴露内部
            # 细节"是同一条边界。
            print(f"error: could not start the Petstore assistant ({exc})", file=sys.stderr)
            # 同样地,以退出码 2 结束整个程序;"from exc" 保留原始异常作为
            # "这个 SystemExit 的成因",方便真正需要调试的人顺着异常链找到
            # 根本原因(尽管普通用户只会看到上面那一行简单的错误信息)。
            raise SystemExit(2) from exc

    # asyncio.run(_main()):Python 标准库提供的"启动一个新的异步事件循环、
    # 运行给定的这个协程直到它完成、然后关闭事件循环"的标准入口——这一行
    # 就是"同步的 main() 函数"和"异步的 _main() 协程"之间真正的桥梁。
    asyncio.run(_main())


# 同上文 server.py 里解释过的写法:只有这个文件被直接运行时,
# __name__ == "__main__" 才成立,才会真的调用 main() 启动整个 CLI。
if __name__ == "__main__":
    main()
