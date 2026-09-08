# pet-mcp

A fyrm onboarding project.

`pet-mcp` is a Model Context Protocol tool server built on FastMCP. The console script
`pet-mcp` starts the server defined in `pet_mcp.server` over stdio, so an MCP client owns
the process lifecycle. Each tool's signature and docstring are its interface, because that is what the
calling model sees.

## Running locally

```bash
make install          # uv sync + pre-commit install
make check            # lockfile, pre-commit hooks, mypy, deptry
make test             # pytest with coverage
make run              # uv run pet-mcp
```

The whole stack comes up with compose:

```bash
docker compose up -d --build
docker compose logs -f app
```

## Observability

Logs are stdlib logging (`LOG_FORMAT=json` for a shipper) with a correlation id on every record.
Telemetry is Pydantic Logfire and is token-gated: without `LOGFIRE_TOKEN` nothing is configured and
nothing leaves the process, so an unconfigured environment is a normal state rather than an error. See
[Operations](operations.md) for the triage details.

## Documentation map
- [Operations](operations.md) — deploying, health endpoints, log and correlation-id triage, schema changes.
- [Private dependencies](private-dependencies.md) — tokens for private fyrm git dependencies.
- [Decisions](decisions/index.md) — the choices that outlive the pull request that made them.
- [Modules](modules.md) — API reference generated from the docstrings.

This project was generated from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen); its
scaffolding (build, lint, CI, container and docs configuration) is updated with `uvx copier update --trust`
rather than edited here.
