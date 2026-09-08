# pet-agent

A fyrm onboarding project.

`pet-agent` is a Pydantic AI agent service. The console script `pet-agent` runs the CLI, the
agent and its tools live in `pet_agent.agent`, and the provider factory in `pet_agent.llm.client`
selects the backend from `LLM_BACKEND` (`anthropic`, `openai`, `openai_compat`, `azure` or `none`). System
prompts are Markdown files under `pet_agent/llm/prompts/`. The LLM is advisory: with missing or
incomplete provider configuration the factory logs a warning and returns `None` instead of raising, so
callers degrade rather than crash.

## Running locally

```bash
make install          # uv sync + pre-commit install
make check            # lockfile, pre-commit hooks, mypy, deptry
make test             # pytest with coverage
make run              # uv run pet-agent
make config-check     # print the resolved settings, secrets masked
```

Before the first run, create the profile file for the environment you are in and fill in its values:

```bash
cp .env.test.example .env.test
APP_ENV=dev make run
```

The whole stack, including Postgres, comes up with compose:

```bash
docker compose up -d --build
docker compose logs -f app
```

## Configuration in one paragraph

Settings come from the process environment plus two dotenv files, layered by `load_env_files()` in
`pet_agent.config`: the process environment wins, then `.env.$APP_ENV` (the gitignored profile file
holding secrets and per-environment values), then `.env.shared` (committed, non-secret defaults). `APP_ENV`
is `dev`, `test` or `production` and is read from the process environment only. A personal `.env` is never
read, and under pytest no file is read at all, so the suite cannot depend on local machine state.
`enforce_production_settings()` refuses to start a production process with unsafe configuration.

`make config-check` prints what a process actually resolved, with secrets masked. The full variable
reference, including which values are secret and which are required in production, is in
[Configuration](configuration.md).

## Observability

Logs are stdlib logging (`LOG_FORMAT=json` for a shipper) with a correlation id on every record.
Telemetry is Pydantic Logfire and is token-gated: without `LOGFIRE_TOKEN` nothing is configured and
nothing leaves the process, so an unconfigured environment is a normal state rather than an error. See
[Operations](operations.md) for the triage details.

## Persistence

Raw SQL over asyncpg: `create_pool(dsn)` plus `apply_schema()`, which applies the idempotent `init.sql` on
every start. No ORM and no migration framework, so schema changes are additive by convention. Postgres
integration tests are gated on `TEST_DATABASE_URL` and skip when it is unset.

## Documentation map

- [Configuration](configuration.md) — every environment variable, the layering rules, and the production gate.
- [Operations](operations.md) — deploying, health endpoints, log and correlation-id triage, schema changes.
- [Private dependencies](private-dependencies.md) — tokens for private fyrm git dependencies.
- [Decisions](decisions/index.md) — the choices that outlive the pull request that made them.
- [Modules](modules.md) — API reference generated from the docstrings.

This project was generated from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen); its
scaffolding (build, lint, CI, container and docs configuration) is updated with `uvx copier update --trust`
rather than edited here.
