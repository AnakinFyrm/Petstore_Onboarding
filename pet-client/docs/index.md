# pet-client

Petstore HTTP client for the Agentic Petstore onboarding project.

`pet-client` is an importable library; it ships no runtime service code and no entrypoint. It is typed
(`py.typed` is included), so consumers type-check against it.

## Running locally

```bash
make install          # uv sync + pre-commit install
make check            # lockfile, pre-commit hooks, mypy, deptry
make test             # pytest with coverage
```

## Documentation map
- [Private dependencies](private-dependencies.md) — tokens for private fyrm git dependencies.
- [Decisions](decisions/index.md) — the choices that outlive the pull request that made them.
- [Modules](modules.md) — API reference generated from the docstrings.

This project was generated from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen); its
scaffolding (build, lint, CI, container and docs configuration) is updated with `uvx copier update --trust`
rather than edited here.
