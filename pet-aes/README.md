# pet-aes

[![Build status](https://img.shields.io/github/actions/workflow/status/fyrm-ai/pet-aes/main.yml?branch=main)](https://github.com/fyrm-ai/pet-aes/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/fyrm-ai/pet-aes/branch/main/graph/badge.svg)](https://codecov.io/gh/fyrm-ai/pet-aes)

Generic Agentic Enterprise System (AES) building blocks: agent spec/registry and MCP toolset wiring, adapted for the Petstore onboarding project.

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

This is a library: import `pet_aes` from your own code. There is no
runtime service entrypoint.

## Documentation

```bash
make docs         # serve the MkDocs site locally
make docs-test    # strict build, fails on warnings
```

The site is deployed to GitHub Pages when a release is published.


## Security scanning

`make audit` checks the locked dependency tree against the advisory database.
CI additionally runs zizmor over the workflow definitions, weekly and on every pull request. All of it is report-only — findings
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
