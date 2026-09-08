# /// script
# requires-python = ">=3.12"
# dependencies = ["litellm>=1.55", "openai>=1.0"]
# ///
"""One-off smoke test: confirm Litellm can reach the chosen model through OpenRouter.

一次性冒烟测试:确认 Litellm 能够通过 OpenRouter 访问选定的模型。

This is step 5 of the onboarding journey ("申请并准备 Litellm 访问权限"): prove
the credential works and stays out of source control, before step 6 wires it
into the real Pydantic AI agent-service project.
这是入门项目第 5 步("申请并准备 Litellm 访问权限"):在第 6 步把这个凭证
正式接入真正的 Pydantic AI agent-service 项目之前,先证明这个凭证是能用的,
并且全程不进入版本控制。

Why "litellm" + an "openrouter/" model prefix, rather than calling OpenRouter's
API directly: the onboarding spec requires model access to go through Litellm,
not straight to a provider. Litellm has built-in support for OpenRouter as one
of its backend providers - prefixing the model name with "openrouter/" tells
Litellm to route the call to OpenRouter using this key, while every call site
in the eventual agent still only ever talks to the `litellm` library's own
unified interface, never to OpenRouter's API shape directly. If the org's
Litellm setup is later pointed at a different provider (or a self-hosted
Litellm proxy) instead of OpenRouter, only this configuration changes - not
any calling code.
为什么用 "litellm" 库配合 "openrouter/" 模型前缀,而不是直接调用 OpenRouter
的 API:入门项目文档要求模型访问必须经过 Litellm,而不是直接连到某个具体
提供商。Litellm 内置支持把 OpenRouter 作为它的后端提供商之一——在模型名前面
加上 "openrouter/" 前缀,就是在告诉 Litellm 用这把 key 把请求路由到
OpenRouter;与此同时,以后 agent 里的每一处调用代码,始终只对接 `litellm`
库自己统一的接口,从来不会直接对接 OpenRouter 的 API 形状。如果以后组织的
Litellm 配置换成了别的提供商(或者换成自建的 Litellm 代理),需要改的只是
这一处配置,不需要改任何调用代码。

How to run (from your own terminal, never paste the key into chat):
运行方式(在你自己的终端里跑,永远不要把密钥贴进聊天里):

    Bash / macOS / Linux:
        OPENROUTER_API_KEY=sk-or-v1-... uv run verify_litellm.py

    Windows PowerShell:
        $env:OPENROUTER_API_KEY = "sk-or-v1-..."
        uv run verify_litellm.py

`uv run` reads the PEP 723 inline metadata block above and installs `litellm`
into a disposable, isolated environment just for this one script - it does not
touch any of the pet-* projects' own dependencies or virtual environments.
`uv run` 会读取上面这段 PEP 723 内联元数据,专门为这一个脚本装一个一次性的、
隔离的环境来安装 `litellm`——不会碰到任何 pet-* 项目自己的依赖或虚拟环境。

Security notes - read before running:
安全注意事项——运行前请先看一遍:

    - This script never prints the API key, and only prints a short prefix of
      the model's reply (not the full completion) to keep terminal output
      boring and safe to screenshot.
      这个脚本从不打印 API key,也只打印模型回复的一小段开头(不打印完整
      回复),这样终端输出保持简单,即使被截图也不会泄漏敏感信息。
    - Do not commit this script's output, and do not add the key to any file
      that could be committed (.env is fine locally; .env.example, source
      code, and Dockerfiles are not).
      不要把这个脚本的输出提交到 git 里,也不要把密钥写进任何可能被提交的
      文件(本地的 .env 文件没问题;但 .env.example、源代码、Dockerfile 都
      不行)。
    - Delete or rotate this key immediately if it is ever pasted into a chat,
      a screenshot, a log, or committed by accident.
      如果这个密钥不小心被贴进过聊天、截图、日志,或者被误提交过,应立即
      作废并重新生成。
"""

import os
import sys

import litellm
import openai

# The onboarding spec's model access must go through Litellm - this constant
# is the one place that says "which model, via which provider" for this
# smoke test. The "openrouter/" prefix is what tells Litellm to route through
# OpenRouter rather than any other configured provider.
# 入门项目文档要求模型访问必须经过 Litellm——这个常量就是这次冒烟测试里唯一
# 说明"用哪个模型、通过哪个提供商"的地方。"openrouter/" 前缀就是告诉 Litellm
# 把请求路由到 OpenRouter,而不是任何其他已配置的提供商。
MODEL = "openrouter/z-ai/glm-5.3-flash"


def main() -> int:
    # Fail with a clear, actionable message if the key is missing - and,
    # critically, never print the key's value even when it IS set.
    # 密钥缺失时,给出一条清晰、可操作的错误提示——并且在密钥确实存在的
    # 情况下,永远不要打印它的值。
    if not os.environ.get("OPENROUTER_API_KEY"):
        print(
            "OPENROUTER_API_KEY is not set. Set it in your shell for this run only, "
            "e.g. `OPENROUTER_API_KEY=sk-or-v1-... uv run verify_litellm.py` - "
            "never paste the key value anywhere else.",
            file=sys.stderr,
        )
        return 1

    print(f"Calling {MODEL} through litellm ...")
    try:
        response = litellm.completion(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly one short sentence confirming you received this test message.",
                }
            ],
            timeout=15,
        )
    except litellm.exceptions.AuthenticationError:
        # Deliberately does not include the underlying exception's message:
        # some providers echo back part of the request/key in error bodies.
        # 这里故意不带上底层异常自己的 message:有些提供商的错误响应体里会
        # 把请求内容/密钥的一部分原样带回来。
        print(
            "Authentication failed - the key was rejected. Double-check it was copied "
            "correctly and has not been revoked/rotated.",
            file=sys.stderr,
        )
        return 1
    except litellm.exceptions.NotFoundError:
        print(
            f"Model '{MODEL}' was not found or is not available on this account. "
            "Confirm the exact model id with Merijn/OpenRouter's model list.",
            file=sys.stderr,
        )
        return 1
    except litellm.exceptions.APIConnectionError as exc:
        print(f"Could not reach the provider (network issue): {exc}", file=sys.stderr)
        return 1
    except openai.OpenAIError as exc:
        # Every litellm exception ultimately derives from openai.OpenAIError
        # (confirmed by inspecting the exception hierarchy directly), so this
        # is the safety net for any error shape not specifically handled
        # above - e.g. a provider/gateway returning an unexpected status code.
        # Only the exception type and status code are printed, never the raw
        # message body, since some gateways echo request details in error
        # responses.
        # 每一个 litellm 异常最终都是 openai.OpenAIError 的子类(直接检查过
        # 异常继承关系确认过这一点),所以这是一道兜底网,用来接住上面没有
        # 专门处理的任何错误形态——比如某个提供商/网关返回了一个意料之外的
        # 状态码。这里只打印异常类型和状态码,从不打印原始的消息内容,因为
        # 有些网关会在错误响应里把请求细节原样带回来。
        status_code = getattr(exc, "status_code", "unknown")
        print(
            f"Call failed ({type(exc).__name__}, status_code={status_code}). "
            "This could be the model id, the key, or a network/gateway issue - "
            "check with Merijn if it's not immediately obvious which.",
            file=sys.stderr,
        )
        return 1

    reply = response.choices[0].message.content or ""
    # Print only a short prefix, not the full reply: this keeps terminal
    # output short and avoids ever needing to worry about what a model might
    # echo back.
    # 只打印回复的一小段开头,不打印完整内容:这样终端输出简短,也不用
    # 担心模型会把什么内容原样回显出来。
    preview = reply[:120] + ("..." if len(reply) > 120 else "")
    print(f"Success. Model replied: {preview!r}")
    print(f"Tokens used: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
