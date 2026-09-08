# pet-mcp

[![Build status](https://img.shields.io/github/actions/workflow/status/fyrm-ai/pet-mcp/main.yml?branch=main)](https://github.com/fyrm-ai/pet-mcp/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/fyrm-ai/pet-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/fyrm-ai/pet-mcp)

A fyrm onboarding project.

## Quickstart

```bash
git init -b main
git add . && git commit -m "Initial project structure from fyrm-template-gen"
make install    # uv sync + pre-commit install
make check      # lockfile, pre-commit hooks, mypy, deptry
make test       # pytest with coverage
```

`make install` creates the `uv.lock` file; commit it — CI expects it to be present.

## Running

```bash
make run    # uv run pet-mcp
```

Starts the MCP (Model Context Protocol) tool server.

## Docker

```bash
make docker-build    # docker build -t pet-mcp .
```

`docker-compose.yml` (dev) and `docker-compose.prod.yml` follow the same
`.env.shared` / `.env.$APP_ENV` layering convention.

## Documentation

```bash
make docs         # serve the MkDocs site locally
make docs-test    # strict build, fails on warnings
```

The site is deployed to GitHub Pages when a release is published.

## Private dependencies

This project is wired for private fyrm git dependencies (GH_DEP_TOKEN in CI,
BuildKit secret in Docker); see `docs/private-dependencies.md` for the runbook.


## Security scanning

`make audit` checks the locked dependency tree against the advisory database.
CI additionally runs zizmor over the workflow definitions and Trivy over the
built image, weekly and on every pull request. All of it is report-only — findings
annotate the run, they do not block a merge.

Dependabot alerts are a separate thing and are off until someone enables them in
Settings > Advanced Security; do that once, per repository.

## Licence

Proprietary. Copyright (c) fyrm.ai, all rights reserved — see `LICENSE`. This is
internal software and is not published to any package index; `pyproject.toml`
carries the `Private :: Do Not Upload` classifier so an accidental upload is
refused.

## Template updates

This project was generated from
[fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen). Pull in
template improvements later with:

```bash
uvx copier update --trust
```
