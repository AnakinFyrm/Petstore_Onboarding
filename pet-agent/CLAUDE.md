# CLAUDE.md

Working agreement for AI coding agents in this repository: what the project is, the commands
that matter, and the conventions `make check` enforces. Human-facing documentation is in
`README.md` and `docs/`.

## What this project is

A fyrm onboarding project.

`pet-agent` is a Pydantic AI agent service. Modules under `src/pet_agent/`:

- `agent.py` — `AgentDeps`, `build_agent(model) -> Agent[AgentDeps, str]` (a factory, so any model
  including `TestModel` can be injected), `run_agent(question)`.
- `cli.py` — console script `pet-agent`; sets one correlation id per run, then asks the agent.
- `llm/client.py` — `create_llm(settings) -> Model | None` provider factory (`anthropic`, `openai`,
  `openai_compat`, `azure`, `none`) that never raises, plus `structured_call()` for schema-validated
  one-shot calls.
- `llm/schemas.py` — deliberately loose output schemas (optional strings) validated strictly afterwards.
- `llm/prompts/*.md` — prompts as Markdown, loaded at import as `<STEM>_PROMPT` constants.
- `config.py` — `Settings` (standard fields via fyrm-service-core mixins, plus the computed
  `llm_enabled` gate), cached `get_settings()`, `enforce_production_settings()`; env-file layering is
  `fyrm_service_core.envfiles`.
- `logging_config.py` — re-exports `fyrm_service_core.logging_config`: text/json, correlation id,
  redaction on by default (exact key match; a secret interpolated into the message string is not
  caught). Change behaviour in the library, not here.
- `alerting.py` — `Alerter` protocol with `LogAlerter` / `NullAlerter`, for the cases where a human
  must act.
- `observability.py` — `setup_telemetry(settings) -> bool`; token-gated and fail-open, and it turns on
  pydantic-ai's agent, tool and token-usage spans.
- `db.py` — `create_pool()` (retrying), `check_connection()` and `apply_schema()`, which applies the
  idempotent `init.sql` at startup.

Invariants: tools receive dependencies through `RunContext[AgentDeps]`, never through globals; every
agent run carries `UsageLimits` so a loop cannot burn an unbounded number of requests; every run sets a
correlation id so its tool calls and retries can be pulled out of the logs; guarantees (validation,
grounding, approval of irreversible actions) live in code at the tool boundary, never in the prompt text.

## Commands

| Command | What it runs |
|---|---|
| `make install` | `uv sync` plus `uv run pre-commit install`. Creates `uv.lock`; commit it. |
| `make check` | `uv lock --locked`, `pre-commit run -a` (ruff, gitleaks, codespell, mypy, deptry, compileall), `mypy`, `deptry src`. |
| `make test` | `pytest` with coverage (`fail_under = 50`). |
| `make run` | `uv run pet-agent` — the agent CLI; takes the question as its argument. |
| `make config-check` | Prints the resolved settings with secrets masked. First thing to run when configuration is suspect. |
| `make docs-test` | `mkdocs build -s` (strict; warnings are errors). Run it when you touch `docs/`. |
| `make docs` | Serves the docs locally. Blocks, so avoid it in an automated session. |
| `make docker-build` | `docker build -t pet-agent .` |
| `make bump` | `cz bump --changelog`: version bump, changelog and tag from the commit history. Only when a release was asked for. |

Narrower loops while iterating: `uv run pytest tests/test_<module>.py::<test> -x`, `uv run mypy`,
`uv run ruff check .`, `uv run ruff format .`. Always through `uv run`; never `pip install`, and never
activate a virtualenv by hand. Add dependencies with `uv add <pkg>` / `uv add --dev <pkg>` so
`pyproject.toml` and `uv.lock` stay in step.

The pre-commit hooks run on commit, and pytest runs again at pre-push, so a push with failing tests is
rejected locally.

## Hard rules

These are not preferences; `make check` fails on most of them and review catches the rest.

- No `from __future__ import annotations` anywhere. This project is Python 3.14-only.
- No decorative separators (`# ---`, `###`) and no emojis — in code, comments, docstrings, log messages,
  Makefile echoes, commit messages or documentation.
- Fully typed. mypy runs `strict = true` with `warn_unreachable` over both `src` and `tests`. A
  `# type: ignore[code]` or `# noqa: RULE` needs the code *and* a short reason on the same line.
  The one blessed exception is the asyncpg pool, typed `Any` because asyncpg ships no stubs.
- ruff at 120 columns with the house rule selection. Consequences worth remembering: timezone-aware
  datetimes only (`datetime.now(tz=UTC)`), `pathlib` instead of `os.path`, lazy `%s` logging arguments
  instead of f-strings, no unused arguments, no bare `except`.
- Comments explain constraints the code cannot express. Do not narrate what the next line does.
- Every behaviour change ships with a test. Tests live in `tests/test_<module>.py` and mirror the module
  they cover.
  Async tests need no decorator (`asyncio_mode = "auto"` is set).
- Public functions and classes keep docstrings; mkdocstrings renders them into the docs site.
- No secrets in code, in tests, in logs or in committed files. gitleaks runs on every commit.
- In a GitHub Actions workflow, never write `${{ secrets.X }}` or `${{ inputs.X }}` inside a `run:` body.
  The expression is substituted into the script before the shell parses it, so the value becomes code.
  Pass it through `env:` and reference the variable. Every `actions/checkout` sets
  `persist-credentials: false`, and every workflow declares `permissions`; zizmor checks all three.

## Configuration model

Three layers, highest priority first:

1. the real process environment (`export`, `docker run -e`, compose `environment:`)
2. `.env.$APP_ENV` — the gitignored profile file: secrets and per-environment values
3. `.env.shared` — committed, non-secret, cross-profile defaults

`APP_ENV` (`dev` | `test` | `production`) is read from the process environment only, so no file can
change which profile loads. A personal `.env` is never read. Files are read from the process working
directory only. A key declared in both files raises a `RuntimeWarning` naming the key. Under pytest no
files are read at all unless a test passes `force=True` to `load_env_files()`.

`Settings` is a `pydantic-settings` model with explicit `Field(validation_alias="SCREAMING_CASE")`
aliases, `SecretStr` for every secret, and `extra="ignore"` — which means a misspelled variable is
silently ignored, so check the alias when a value does not take effect, or run `make config-check` to see
what the process actually resolved. `get_settings()` is `lru_cache`d; in tests either build `Settings()`
directly or call `get_settings.cache_clear()`. `enforce_production_settings()` runs at startup and raises
with every problem listed at once when `APP_ENV` is anything outside
`{dev, development, local, test, testing}` and a security-relevant setting is missing — so
`APP_ENV=staging` is treated as production, deliberately.

To add a setting, do all of these in one change:

1. add the `Field(..., validation_alias="NEW_VAR")` to `Settings`
2. document it in `.env.example` (the committed reference; it is never loaded)
3. put a non-secret default in `.env.shared`, or a placeholder in `.env.test.example` and
   `.env.production.example` when it is secret or environment-specific
4. add `"NEW_VAR"` to `MANAGED_ENV_VARS` in `tests/conftest.py`, or a stray shell variable will leak
   into the suite
5. if it is security-relevant, add a check to `enforce_production_settings()`
6. add the row to `docs/configuration.md`

Never read `os.environ` directly in application code; go through `Settings`. Call `.get_secret_value()`
only at the point of use, never to log or return a secret.

## Persistence

Raw SQL over asyncpg. No ORM, no query builder, no migration framework — do not add one.

- `init.sql` is the schema of record and is applied on **every** start by `apply_schema()`, so every
  statement must be idempotent: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`,
  `CREATE INDEX IF NOT EXISTS`.
- Schema changes are additive. Dropping or retyping a column is not safe to re-run against live data; do
  that by hand, deliberately, with a backup, and keep the code tolerant of rows written by older versions.
- SQL lives in module-level constants next to the function that runs it, always parameterised (`$1`,
  `$2`) — never string-interpolated.
- `create_pool()` retries (`PG_CONNECT_ATTEMPTS`, `PG_CONNECT_BACKOFF_SECONDS`) because a container
  usually starts before the database accepts connections; it still raises after the last attempt, so a
  wrong DSN fails loudly instead of retrying forever.
- A pool object outlives the database behind it, so readiness has to ask: `check_connection(pool)` runs
  `SELECT 1`. Use it rather than assuming a non-`None` pool means a working database.
- Postgres tests are gated on `TEST_DATABASE_URL` and skip when it is unset. They apply the schema and
  write rows, so point it at a disposable database only.

## LLM rules

- Pydantic AI only. Do not introduce LangChain or another agent framework.
- `create_llm()` returns `None` when the backend is disabled, unknown or misconfigured, and never
  raises. Callers must degrade into a working state instead of crashing; the LLM is advisory.
- Prompts are Markdown files in `llm/prompts/`, loaded at import. Add `foo.md` and the matching
  `FOO_PROMPT` constant together — `tests/test_prompts.py` asserts the directory and the exported
  constants stay in sync.
- Keep output schemas loose (optional fields) and apply strict business validation afterwards in code,
  so the model reports what it found instead of inventing values to satisfy a type.
- No live LLM calls in unit tests, ever. Use pydantic-ai's `TestModel` or `FunctionModel`; live runs are
  opt-in, marked tests. Tests must pass with no provider credentials present.

## Logs, correlation ids and alerts

Three separate channels; do not collapse them.

- **Logs** are stdlib logging through `setup_logging(level, log_format)`: `text` for humans, `json` for
  a shipper. Attach structured context with `extra={...}` instead of formatting it into the message.
- **Correlation id** is a `ContextVar` set with `set_correlation_id()`, appended to every record by
  `CorrelationFilter`.
  The CLI sets one per run. Any new entry point does the same.
- **Alerts** are for "a human must act and it will not fix itself": use the `Alerter` protocol from
  `alerting.py` (`LogAlerter` by default, `NullAlerter` in tests). Keep them rare and actionable — an
  alert that fires routinely trains people to ignore it. Do not reach for an alert where a log line or a
  raised exception is the right answer.

## Telemetry

`observability.py` wires up Pydantic Logfire. It is token-gated and fail-open, and it must stay that way:

- No `LOGFIRE_TOKEN` means `setup_telemetry()` configures nothing and returns `False`; nothing leaves the
  process. `TELEMETRY_ENABLED=false` forces it off even with a token. This is the normal state in tests
  and CI, so an absent token is never an error.
- A failure inside setup is logged and swallowed. Telemetry must never be the reason the service does not
  start, and no code path may depend on the exporter being reachable.
- Logfire's console output stays off: this project's own stdout handler owns the terminal, and stdlib
  logging remains the source of truth during an incident.
- Keep secrets and personal data out of span names and attributes. `SCRUB_PATTERNS` covers this
  project's own naming (`dsn`, `signing`, `api_key`, `secret`); extend it rather than trusting call sites.

## Commits and releases

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/) and a commit-msg
hook rejects anything else: `feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`,
`chore:`, with an optional scope (`fix(config): ...`) and `!` for a breaking change. The subject is
imperative, lower case, no trailing period, no emoji, and no AI attribution or co-author trailers.

Versioning is commitizen-driven: `make bump` (`cz bump --changelog`) derives the next version from the
commit history and updates the version, `CHANGELOG.md` and the tag. Never hand-edit the changelog or the
version field, and only bump when a release was actually asked for.
Publishing a GitHub Release `vX.Y.Z` builds and pushes the image; CI fails the release when the tag does
not match the version in `pyproject.toml`.

## This repository is generated

It came from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen) and stays linked to it
through `.copier-answers.yml`. These files are template-owned scaffolding: `Makefile`, `tox.ini`,
`.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`, the `[tool.*]` sections of `pyproject.toml`,
`.github/**`, `Dockerfile`, `.dockerignore`, `docker-compose*.yml`, `mkdocs.yml`, and this file.

Change those upstream in the template and run `uvx copier update --trust` here. Editing them locally
works exactly once: the next `copier update` re-applies the template version and every local edit shows
up as a merge conflict, forever. Never hand-edit `.copier-answers.yml`.

What *is* this repository's own: everything under `src/` and `tests/`, `init.sql`, the page bodies
in `docs/`, the `.env*` files, and the dependency lists in `pyproject.toml` (via `uv add`).

## Definition of done

1. `make check && make test` both green locally, before pushing.
   CI runs the same gates plus a strict docs build and the image build, so there is no reason to
   discover a failure there.
2. New behaviour has tests; changed behaviour has updated tests.
3. Do not commit, push, tag or open a pull request unless you were asked to.
4. Configuration changes land in `.env.example`, `docs/configuration.md` and `tests/conftest.py` in the
   same commit as the `Settings` field.
5. A choice that a reviewer would ask "why?" about — a rejected alternative, a deliberate limitation, a
   dependency taken on for a non-obvious reason — gets a short record in `docs/decisions/`. Not for
   anything the code already says.
