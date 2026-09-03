# syntax=docker/dockerfile:1.7

# Build stage: resolve and install everything with uv.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

# Compile bytecode at build time (faster container startup); copy instead of
# hardlinking because the cache mount lives on a different filesystem.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# git is needed to install dependencies from private git sources.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Private git dependencies need a GitHub token during `uv sync`. Pass it as a
# BuildKit secret so it authenticates git only during the build and is never
# written into an image layer:
#   GH_TOKEN=$(gh auth token) \
#   docker build --secret id=github_token,env=GH_TOKEN -t pet-agent .

# Install dependencies first (cached layer, only invalidated when the lock changes).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=secret,id=github_token \
    sh -eu -c 'if [ -s /run/secrets/github_token ]; then \
        export GIT_CONFIG_COUNT=1 \
               GIT_CONFIG_KEY_0="url.https://x-access-token:$(cat /run/secrets/github_token)@github.com/.insteadOf" \
               GIT_CONFIG_VALUE_0="https://github.com/"; \
      fi; \
      uv sync --frozen --no-install-project --no-dev'

# Then copy the project and install it into the venv (exposes the
# pet-agent console script).
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=github_token \
    sh -eu -c 'if [ -s /run/secrets/github_token ]; then \
        export GIT_CONFIG_COUNT=1 \
               GIT_CONFIG_KEY_0="url.https://x-access-token:$(cat /run/secrets/github_token)@github.com/.insteadOf" \
               GIT_CONFIG_VALUE_0="https://github.com/"; \
      fi; \
      uv sync --frozen --no-dev'

# Runtime stage: plain Python, no uv, no build tooling.
FROM python:3.14-slim-bookworm

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app /app

# Put the venv's console scripts on PATH; UV_NO_SYNC guards against any stray
# `uv run` trying to re-sync inside the container.
ENV PATH="/app/.venv/bin:$PATH" \
    UV_NO_SYNC=1

USER app

# The process handles SIGTERM to drain in-flight work, so the runtime must send it
# rather than the default SIGQUIT for this base image.
STOPSIGNAL SIGTERM

CMD ["pet-agent"]
