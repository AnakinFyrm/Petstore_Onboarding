# CLAUDE.md

Working agreement for AI coding agents in this repository: what the project is, the commands
that matter, and the conventions `make check` enforces. Human-facing documentation is in
`README.md` and `docs/`.

## What this project is

Generic Agentic Enterprise System (AES) building blocks: agent spec/registry and MCP toolset wiring, adapted for the Petstore onboarding project.

`pet-aes` is an importable library: no service entrypoint, no runtime process. `src/pet_aes/example.py`
shows the expected shape (small, typed, pure functions with docstrings) and is meant to be replaced.

Invariants: no import-time side effects and no configuration reading — a library takes its inputs as
arguments; keep the public surface small and typed, since `py.typed` ships and consumers type-check
against it.

## Commands

| Command | What it runs |
|---|---|
| `make install` | `uv sync` plus `uv run pre-commit install`. Creates `uv.lock`; commit it. |
| `make check` | `uv lock --locked`, `pre-commit run -a` (ruff, gitleaks, codespell, mypy, deptry, compileall), `mypy`, `deptry src`. |
| `make test` | `pytest` with coverage (`fail_under = 50`). |
| `make docs-test` | `mkdocs build -s` (strict; warnings are errors). Run it when you touch `docs/`. |
| `make docs` | Serves the docs locally. Blocks, so avoid it in an automated session. |
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
- ruff at 120 columns with the house rule selection. Consequences worth remembering: timezone-aware
  datetimes only (`datetime.now(tz=UTC)`), `pathlib` instead of `os.path`, lazy `%s` logging arguments
  instead of f-strings, no unused arguments, no bare `except`.
- Comments explain constraints the code cannot express. Do not narrate what the next line does.
- Every behaviour change ships with a test. Tests live in `tests/test_<module>.py` and mirror the module
  they cover.
- Public functions and classes keep docstrings; mkdocstrings renders them into the docs site.
- No secrets in code, in tests, in logs or in committed files. gitleaks runs on every commit.
- In a GitHub Actions workflow, never write `${{ secrets.X }}` or `${{ inputs.X }}` inside a `run:` body.
  The expression is substituted into the script before the shell parses it, so the value becomes code.
  Pass it through `env:` and reference the variable. Every `actions/checkout` sets
  `persist-credentials: false`, and every workflow declares `permissions`; zizmor checks all three.

## Commits and releases

Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/) and a commit-msg
hook rejects anything else: `feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `test:`, `build:`, `ci:`,
`chore:`, with an optional scope (`fix(config): ...`) and `!` for a breaking change. The subject is
imperative, lower case, no trailing period, no emoji, and no AI attribution or co-author trailers.

Versioning is commitizen-driven: `make bump` (`cz bump --changelog`) derives the next version from the
commit history and updates the version, `CHANGELOG.md` and the tag. Never hand-edit the changelog or the
version field, and only bump when a release was actually asked for.

## This repository is generated

It came from [fyrm-template-gen](https://github.com/fyrm-ai/fyrm-template-gen) and stays linked to it
through `.copier-answers.yml`. These files are template-owned scaffolding: `Makefile`, `tox.ini`,
`.pre-commit-config.yaml`, `.editorconfig`, `.gitignore`, the `[tool.*]` sections of `pyproject.toml`,
`.github/**`, `.devcontainer/**`, `mkdocs.yml`, and this file.

Change those upstream in the template and run `uvx copier update --trust` here. Editing them locally
works exactly once: the next `copier update` re-applies the template version and every local edit shows
up as a merge conflict, forever. Never hand-edit `.copier-answers.yml`.

What *is* this repository's own: everything under `src/` and `tests/`, the page bodies
in `docs/`, the `.env*` files, and the dependency lists in `pyproject.toml` (via `uv add`).

## Definition of done

1. `make check && make test` both green locally, before pushing.
   CI runs the same gates plus a strict docs build, so there is no reason to
   discover a failure there.
2. New behaviour has tests; changed behaviour has updated tests.
3. Do not commit, push, tag or open a pull request unless you were asked to.
5. A choice that a reviewer would ask "why?" about — a rejected alternative, a deliberate limitation, a
   dependency taken on for a non-obvious reason — gets a short record in `docs/decisions/`. Not for
   anything the code already says.
