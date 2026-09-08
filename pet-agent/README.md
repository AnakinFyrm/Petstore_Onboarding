# pet-agent

[![Build status](https://img.shields.io/github/actions/workflow/status/fyrm-ai/pet-agent/main.yml?branch=main)](https://github.com/fyrm-ai/pet-agent/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/fyrm-ai/pet-agent/branch/main/graph/badge.svg)](https://codecov.io/gh/fyrm-ai/pet-agent)

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

## Configuration

Configuration is read from the process environment plus two committed-or-local
dotenv files, layered by `load_env_files()` in `src/pet_agent/config.py`:

1. The real process environment always wins.
2. `.env.$APP_ENV` (profile file, gitignored): keys that are secret or differ
   between environments. `APP_ENV` is `dev`, `test` or `production` and must be
   set in the process environment, not in a file.
3. `.env.shared` (committed): non-secret defaults shared by every profile.

A personal `.env` is never read, and under pytest no files are loaded unless a
test asks for them explicitly. Duplicate keys across `.env.$APP_ENV` and
`.env.shared` raise a `RuntimeWarning` so drift is caught early.

To set up a profile, copy the matching template and fill in the secrets:

```bash
cp .env.test.example .env.test
cp .env.production.example .env.production
```

`.env.example` documents every environment variable this service understands.
See the generated documentation (`make docs`) for module-level reference.
## PostgreSQL

`src/pet_agent/db.py` (raw SQL over asyncpg, no ORM/migration framework) and
`init.sql` are copier-template scaffolding that this agent does not currently
use - nothing in `agent.py`/`cli.py`/`config.py` imports `db.py`, and this
service has no database of its own (the real Petstore database is owned
exclusively by [petstore-api](../petstore-api); see ONBOARDING.md section 6).
The `postgres` service and `PG_DSN` were removed from this project's Docker
Compose files for the same reason (Step 9). `db.py`/`init.sql` themselves are
left in place, unused, in case a future step needs them - if one does,
`PG_DSN` and a `postgres`/`db` service would need to be reintroduced
deliberately, together with something in `agent.py` that actually calls
`db.py`.

## Running

```bash
make run    # uv run pet-agent
```

Starts an interactive command-line conversation with the Petstore assistant
(ONBOARDING.md section 12, step 8): a welcome message, then a `You: ` prompt
in a loop - describe the kind of pet you want, ask for details, buy one once
you've confirmed, and type `exit`/`quit` (or Ctrl-D) whenever you'd like to
leave. Everything the CLI itself prints is the assistant's own reply text -
no tool call details, no raw model output, no API response bodies, and no
secrets ever reach the terminal (see `src/pet_agent/cli.py`).

The LLM provider is selected with `LLM_BACKEND` (`anthropic`, `openai`,
`openai_compat`, `azure` or `none`); with `LLM_BACKEND=none` or an incomplete
provider config, `make run` refuses to start and prints a one-line error
instead of opening a broken conversation. To use OpenRouter, set
`LLM_BACKEND=openai_compat`, `OPENAI_BASE_URL=https://openrouter.ai/api/v1`,
`OPENAI_API_KEY` to an OpenRouter key, and `LLM_MODEL` to an OpenRouter model
id - see `.env.example`.

## Talking to the Petstore (pet-mcp)

This agent never talks to petstore-api, a database, or anything else on its
own: every action comes from the [pet-mcp](../pet-mcp) MCP server, which it
launches as a stdio subprocess (`uv run --project $PET_MCP_PROJECT_DIR
pet-mcp` - the same command pet-mcp's own `make run` uses). Point
`PET_MCP_PROJECT_DIR` at wherever your pet-mcp checkout lives (a sibling
directory by default) and `PETSTORE_API_BASE_URL` at the running
petstore-api; both are documented in `.env.example`. There are no local
`@agent.tool` functions in this codebase on purpose - see
`src/pet_agent/agent.py`.

## Docker

**For the complete system (database + petstore-api + pet-agent, one command),
see the top-level `../README.md` and `../docker-compose.yml` instead - that is
the documented startup journey for ONBOARDING.md section 12, step 9.** What
follows here is for building/running pet-agent on its own.

This image bundles [pet-mcp](../pet-mcp) inside it: pet-agent launches pet-mcp
as a stdio subprocess exactly as it does outside Docker (see "Talking to the
Petstore" above), so both live in one container rather than two. Because
pet-agent depends on [pet-aes](../pet-aes) and pet-mcp depends on
[pet-client](../pet-client) - both local, editable, sibling-directory
dependencies - the Docker build context has to be the shared parent
directory, not this one; see `Dockerfile`'s own top comment for the full
reasoning.

```bash
make docker-build    # cd .. && docker build -f pet-agent/Dockerfile -t pet-agent .
```

`docker-compose.yml` (dev) and `docker-compose.prod.yml` in this directory are
a developer convenience for running pet-agent by itself (both already point
their `build.context` at `..` for the same reason); both follow the same
`.env.shared` / `.env.$APP_ENV` layering convention, and neither runs its own
database (see "PostgreSQL" above).

pet-mcp's own standalone `Dockerfile`/`docker-compose.yml` in `../pet-mcp` are
not part of this architecture (pet-mcp is bundled into this image, not
deployed on its own) and are currently unused.

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
