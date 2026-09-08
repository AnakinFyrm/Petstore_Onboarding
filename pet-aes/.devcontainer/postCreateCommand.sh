#!/usr/bin/env bash
# Devcontainer setup, run once after the container is created.
#
# The uv cache lives on a named volume (see devcontainer.json) so rebuilding the
# container does not re-download every wheel. Docker creates that volume owned by
# root, so it has to be claimed for the container user before uv writes to it;
# under Podman with --userns=keep-id the host user is mapped through and the
# chown is a no-op.
set -euo pipefail

# uv installs itself here, and the installer only edits shell profiles, which
# this non-interactive script never reads.
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv > /dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

cache_dir="${UV_CACHE_DIR:-$HOME/.cache/uv}"
if [ ! -w "$cache_dir" ]; then
  if command -v sudo > /dev/null 2>&1; then
    sudo mkdir -p "$cache_dir"
    sudo chown -R "$(id -u):$(id -g)" "$cache_dir"
  else
    mkdir -p "$cache_dir"
  fi
fi

uv sync
uv run pre-commit install --install-hooks
