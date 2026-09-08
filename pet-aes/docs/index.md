# pet-aes

Generic Agentic Enterprise System (AES) building blocks: agent spec/registry and MCP toolset wiring, adapted for the Petstore onboarding project.

`pet-aes` is an importable library; it ships no runtime service code and no entrypoint. It is typed
(`py.typed` is included), so consumers type-check against it.

## Running locally

```bash
make install          # uv sync + pre-commit install
make check            # lockfile, pre-commit hooks, mypy, deptry
make test             # pytest with coverage
```

Alternatively open the repository in the VS Code devcontainer: it installs uv, syncs the environment and
installs the pre-commit hooks on create, and keeps the uv cache in a named volume so later rebuilds are
fast.

## Documentation map
- [Decisions](decisions/index.md) — the choices that outlive the pull request that made them.
- [Modules](modules.md) — API reference generated from the docstrings.

This project was generated from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen); its
scaffolding (build, lint, CI, container and docs configuration) is updated with `uvx copier update --trust`
rather than edited here.
