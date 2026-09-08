# syntax=docker/dockerfile:1.7
#
# Combined image for pet-agent + pet-mcp (ONBOARDING.md Section 12, Step 9).
#
# pet-agent talks to pet-mcp by launching it as a stdio *subprocess*
# (`pet_agent.agent.build_pet_mcp_toolset`: `uv run --project <dir> pet-mcp`),
# never over a network transport - so, per the chosen Step 9 architecture,
# both live in ONE image/container rather than two, and that stdio-subprocess
# wiring is left completely unchanged from local dev.
#
# pet-agent (Step 7) and pet-mcp (Step 2) each declare an *editable, local
# path* dependency on a sibling project - pet-aes ("../pet-aes") and
# pet-client ("../pet-client") respectively. Docker's build context only ever
# reaches into the directory tree passed to `docker build`, so a Dockerfile
# living in (and built with the context of) a single project can never see
# its sibling. That is why THIS Dockerfile must be built with the shared
# parent directory as its context - not `pet-agent/` alone:
#
#   cd .. && docker build -f pet-agent/Dockerfile -t pet-agent .
#
# (the top-level docker-compose.yml one level up does exactly this, and is
# the documented, normal way to build this image - see its own comments and
# the top-level README).
#
# 本镜像把 pet-agent 和 pet-mcp 打进同一个镜像/容器里(对应 ONBOARDING.md 第
# 12 节第 9 步)。
#
# pet-agent 跟 pet-mcp 对话的方式,是把 pet-mcp 当作一个 stdio *子进程*启动
# (`pet_agent.agent.build_pet_mcp_toolset`:`uv run --project <目录> pet-mcp`),
# 从来不走网络传输——所以按照已经确定的第 9 步架构,两者放进同一个
# 镜像/容器,而不是拆成两个,而且这套 stdio 子进程的接线方式跟本地开发时完全
# 一样,不做任何改动。
#
# pet-agent(第 7 步)和 pet-mcp(第 2 步)都各自声明了一个*可编辑的本地路径*
# 依赖,分别指向兄弟项目——pet-aes("../pet-aes")和 pet-client
# ("../pet-client")。Docker 的构建上下文(build context)只能触达传给
# `docker build` 的那棵目录树,所以如果 Dockerfile 只用自己项目自己的目录做
# 上下文,就永远看不到它的兄弟项目。这就是为什么这份 Dockerfile 必须用共同的
# 父目录作为构建上下文来构建——而不是单用 `pet-agent/`:
#
#   cd .. && docker build -f pet-agent/Dockerfile -t pet-agent .
#
# (上一级目录的顶层 docker-compose.yml 就是这么做的,也是本项目文档规定的、
# 正常构建这个镜像的方式——细节见它自己的注释和顶层 README。)

# ---- Build stage: resolve and install pet-mcp and pet-agent, each into its
# own venv, built from its own lockfile exactly as it would be outside
# Docker. ----
# ---- 构建阶段:把 pet-mcp 和 pet-agent 分别装进各自的 venv,各自用自己的
# 锁文件构建——跟不在 Docker 里跑时完全一样。----
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

# Compile bytecode at build time (faster container startup); copy instead of
# hardlinking because the cache mount lives on a different filesystem.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# All four sibling projects, at the same relative layout their pyproject.toml
# / uv.lock files already expect (pet-mcp's "../pet-client", pet-agent's
# "../pet-aes") - this only works because the build context is the shared
# parent directory (see the note above).
#
# No private-git BuildKit-secret handling is needed here (unlike the
# standalone per-project Dockerfiles this one replaces for pet-agent): every
# dependency these two projects need to sync is either on a public index or
# one of these four local path dependencies.
# 这四个兄弟项目按各自 pyproject.toml / uv.lock 已经预期的相对路径布局复制进
# 来(pet-mcp 的 "../pet-client"、pet-agent 的 "../pet-aes")——这只有在构建
# 上下文是共同的父目录时才成立(见上面的说明)。
#
# 这里不需要处理私有 git 依赖的 BuildKit secret(不同于本文件所取代的、
# pet-agent 原来那份单项目 Dockerfile):这两个项目要 sync 的每一个依赖,要么
# 在公共索引上,要么就是这四个本地路径依赖之一。
COPY pet-client pet-client
COPY pet-aes pet-aes
COPY pet-mcp pet-mcp
COPY pet-agent pet-agent

# pet-mcp is launched as its own OS subprocess at runtime, so it needs its own
# venv - this is a real `uv run --project pet-mcp pet-mcp`, the exact command
# pet-mcp's own README documents, not an in-process import.
# pet-mcp 在运行时是被当作独立的操作系统子进程启动的,所以它需要自己的
# venv——这里跑的是一次真正的 `uv run --project pet-mcp pet-mcp`,跟 pet-mcp
# 自己 README 里写的运行方式完全一样,不是进程内的 import。
RUN --mount=type=cache,target=/root/.cache/uv \
    cd pet-mcp && uv sync --frozen --no-dev

# pet-agent gets its own venv the same way; this is what installs the
# `pet-agent` console script the runtime stage's CMD below invokes.
# pet-agent 也用同样的方式装进自己的 venv;下面运行阶段 CMD 调用的
# `pet-agent` 这个控制台脚本,就是这一步装进去的。
RUN --mount=type=cache,target=/root/.cache/uv \
    cd pet-agent && uv sync --frozen --no-dev


# ---- Runtime stage. ----
# ---- 运行阶段。----
#
# Unlike a single-project deployment (petstore-api's own Dockerfile, or the
# standalone pet-mcp/pet-agent Dockerfiles this one replaces), the runtime
# stage here keeps `uv` itself, rather than stripping down to bare
# `python:3.14-slim-bookworm` - because pet-agent starts pet-mcp at runtime by
# actually running `uv run --project /app/pet-mcp pet-mcp` as a real
# subprocess (see pet_agent.agent.build_pet_mcp_toolset and the test that
# pins this exact command shape,
# test_build_pet_mcp_toolset_wires_command_and_env). Staying on this same
# uv-provided base for both stages is the simplest way to guarantee `uv` is
# on PATH at runtime.
# 跟单项目部署不一样(petstore-api 自己的 Dockerfile,或者本文件所取代的、
# pet-mcp/pet-agent 各自独立的 Dockerfile),这里的运行阶段保留了 `uv` 本身,
# 而不是精简成裸的 `python:3.14-slim-bookworm`——因为 pet-agent 在运行时会真
# 的去跑 `uv run --project /app/pet-mcp pet-mcp` 这样一个真实子进程(见
# pet_agent.agent.build_pet_mcp_toolset,以及固定了这个确切命令形状的测试
# test_build_pet_mcp_toolset_wires_command_and_env)。两个阶段都用同一个自带
# uv 的基础镜像,是保证运行时 `uv` 在 PATH 上最简单的办法。
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS runtime

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app

WORKDIR /app

# The FULL builder /app directory - source and venvs for all four projects -
# is copied in, not just the two venvs. This is required, not just
# convenient: pet-mcp's and pet-agent's editable installs of pet-client and
# pet-aes point at those sibling *source* directories by path (that is what
# `editable = true` means), so pet-client/ and pet-aes/ must still exist at
# the same paths at runtime or those imports fail. `uv run --project
# pet-mcp pet-mcp` also re-reads pet-mcp/pyproject.toml at launch, so
# pet-mcp/ itself must be a real project directory here too, not just its
# .venv.
# 这里复制进来的是构建阶段整个 /app 目录——四个项目的源码和 venv 全都要,而
# 不只是两个 venv。这不是图省事,而是必须的:pet-mcp 和 pet-agent 里对
# pet-client、pet-aes 的可编辑安装,是按路径指向那两个兄弟项目的*源码*目录的
# (这正是 `editable = true` 的含义),所以 pet-client/、pet-aes/ 在运行时也
# 必须原样存在于同样的路径下,否则这些 import 会失败。另外 `uv run --project
# pet-mcp pet-mcp` 启动时还会重新读一遍 pet-mcp/pyproject.toml,所以这里的
# pet-mcp/ 本身也得是一个真正的项目目录,不能只留下它的 .venv。
COPY --from=builder --chown=app:app /app /app

# Put pet-agent's own venv's console scripts on PATH (this is what makes
# `pet-agent` resolve as CMD below); UV_NO_SYNC guards both `pet-agent` itself
# and the `uv run --project /app/pet-mcp pet-mcp` subprocess it launches
# against ever trying to re-resolve/re-sync from the network inside the
# container. PET_MCP_PROJECT_DIR is set to this image's own absolute path to
# the bundled pet-mcp checkout - the same variable, and the same
# `uv run --project <dir> pet-mcp` command, used outside Docker, just
# pointed at where pet-mcp actually lives in this image.
# 把 pet-agent 自己 venv 里的控制台脚本放到 PATH 上(这样下面 CMD 里的
# `pet-agent` 才能被找到);UV_NO_SYNC 同时防止 `pet-agent` 自己、以及它启动
# 的 `uv run --project /app/pet-mcp pet-mcp` 子进程,在容器里尝试联网重新
# 解析/同步。PET_MCP_PROJECT_DIR 被设成本镜像里 pet-mcp 检出的绝对路径——跟
# 在 Docker 之外用的是同一个变量、同一条 `uv run --project <目录> pet-mcp`
# 命令,只是这次指向的是 pet-mcp 在这个镜像里真正所在的位置。
ENV PATH="/app/pet-agent/.venv/bin:$PATH" \
    UV_NO_SYNC=1 \
    PET_MCP_PROJECT_DIR=/app/pet-mcp \
    # The `app` user has no home directory (created with --no-create-home,
    # since it never needs one) - uv's default cache location is
    # $HOME/.cache/uv, which would otherwise fail here with exactly
    # "Permission denied" trying to create /home/app. /tmp is writable by
    # every user in this base image, so pointing the cache there sidesteps
    # needing a home directory at all. UV_NO_SYNC above already means this
    # cache is never actually populated at runtime (no resolving/syncing
    # happens) - uv just needs *a* writable directory to point at.
    # `app` 用户没有自己的 home 目录(创建时用的是 --no-create-home,因为它
    # 本来就不需要)——uv 默认的缓存位置是 $HOME/.cache/uv,这里如果不设置就
    # 会报"Permission denied",原因正是它想创建 /home/app 却创建不了。这个
    # 基础镜像里 /tmp 对所有用户都可写,把缓存指到那里就不再需要一个 home
    # 目录了。上面已经设置的 UV_NO_SYNC 意味着运行时这个缓存实际上从来不会
    # 真的被写入东西(不会发生任何解析/同步)——uv 只是需要*一个*能写的目录
    # 让它指过去。
    UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app/pet-agent
USER app

# The process handles SIGTERM to drain in-flight work, so the runtime must
# send it rather than the default SIGQUIT for this base image.
STOPSIGNAL SIGTERM

CMD ["pet-agent"]
