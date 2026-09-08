# Configuration

Every setting `pet-agent` understands, where to put it, and what happens when it is missing.
The implementation is `src/pet_agent/config.py`; `.env.example` in the repository root is the
committed quick reference.

## Layering

Configuration arrives from three layers, highest priority first:

1. **The process environment** — `export`, `docker run -e`, a compose `environment:` block, a platform
   secret store. Always wins.
2. **`.env.$APP_ENV`** — the profile file for the selected environment (`.env.dev`, `.env.test`,
   `.env.production`). Gitignored, because this is where secrets and per-environment values live. Copy
   `.env.test.example` / `.env.production.example` to create one.
3. **`.env.shared`** — committed, non-secret defaults that are the same in every environment.

Rules that follow from that, all enforced in code:

- `APP_ENV` is read from the process environment only, so no file can change which profile is loaded.
  Set it where you start the process.
- A personal `.env` is never read. A file that quietly differs between machines is a debugging trap.
- Files are read from the **process working directory** only (`/app` in the container image), so an
  unrelated `.env.shared` further up the tree cannot leak in.
- Declaring the same key in both files raises a `RuntimeWarning` naming the key; the profile value wins
  and the shared value is ignored. Move the key to exactly one file.
- Under pytest no env file is read at all unless a test explicitly calls
  `load_env_files(force=True)`, so a developer's local configuration can never change a test result.

`Settings` is a `pydantic-settings` model with `extra="ignore"`, so a **misspelled variable is silently
ignored** rather than rejected. If a value does not take effect, check the spelling against the table
below. `get_settings()` is cached for the process lifetime; changing the environment after the first
call has no effect.

## Variable reference

Secrets are `SecretStr` fields: they never appear in a log line or a `repr`, and code calls
`.get_secret_value()` only at the point of use.

| Variable | Meaning | Default | Secret | Required in production |
|---|---|---|---|---|
| `APP_ENV` | Selects the profile file and the production gate: `dev`, `test`, `production`. | `dev` | no | yes, set it explicitly |
| `LOG_LEVEL` | Root logger level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. | `INFO` | no | no |
| `LOG_FORMAT` | `text` for humans, `json` for a log shipper (one object per line). | `text` | no | no, but `json` is recommended |
| `SERVICE_NAME` | Identifies this process in logs and telemetry. Override when several deployments of the same code must be told apart. | `pet-agent` | no | no |
| `TELEMETRY_ENABLED` | `false` forces telemetry off even when a token is present. | `true` | no | no |
| `LOGFIRE_TOKEN` | Logfire write token. Telemetry is token-gated: unset means nothing is configured and nothing leaves the process. | unset | yes | no, but recommended |
| `LLM_BACKEND` | Provider: `anthropic`, `openai`, `openai_compat`, `azure` or `none`. | `none` | no | yes, and fully configured |
| `LLM_MODEL` | Provider model identifier. | unset (`claude-sonnet-5` for `anthropic`) | no | yes for `openai` and `openai_compat` |
| `ANTHROPIC_API_KEY` | Credential for the `anthropic` backend. | unset | yes | yes when that backend is selected |
| `OPENAI_API_KEY` | Credential for `openai`; optional for `openai_compat` when the gateway needs none. | unset | yes | yes when that backend is selected |
| `OPENAI_BASE_URL` | Base URL of an OpenAI-compatible gateway; only used by `openai_compat`. | unset | no | yes for `openai_compat` |
| `AZURE_OPENAI_API_KEY` | Credential for the `azure` backend. | unset | yes | yes when that backend is selected |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint. | unset | no | yes for `azure` |
| `AZURE_OPENAI_DEPLOYMENT` | Azure deployment name, used as the model name. | unset | no | yes for `azure` |
| `AZURE_OPENAI_API_VERSION` | Azure API version. | `2024-10-21` | no | no |
| `PG_DSN` | `postgresql://user:password@host:5432/dbname`. Percent-encode special characters in the password (a literal `%` becomes `%25`). | unset | yes | yes |
| `PG_POOL_MIN_SIZE` | Minimum asyncpg pool connections. | `1` | no | no |
| `PG_POOL_MAX_SIZE` | Maximum asyncpg pool connections. | `5` | no | no |
| `PG_CONNECT_ATTEMPTS` | How many times startup retries the first connection before giving up, because a container usually starts before the database accepts connections. | `10` | no | no |
| `PG_CONNECT_BACKOFF_SECONDS` | Base delay between those attempts; it grows linearly with the attempt number. | `1.0` | no | no |
| `TEST_DATABASE_URL` | Gate for the Postgres integration tests, read by `tests/conftest.py` and never by `Settings`. Point it at a disposable database. | unset | yes | never set it in production |

Types and ranges are validated by pydantic at startup, so `HTTP_PORT=0` or `PG_POOL_MAX_SIZE=0` fails
immediately with a validation error rather than misbehaving later.

To see what a process actually resolved, including which layer won, run `make config-check`: it prints
every setting with secrets masked. That is the fastest way to settle a "but the value is in the file"
argument during an incident.

## Where each variable belongs

| File | Committed | Contents |
|---|---|---|
| `.env.example` | yes | Documentation only, never loaded. Lists every variable with an example value. |
| `.env.shared` | yes | Non-secret values identical in every environment. |
| `.env.test.example`, `.env.production.example` | yes | Templates for the profile files, with empty secrets. |
| `.env.test`, `.env.production` | no (gitignored) | The real profile values, including secrets. |

In a managed environment, prefer injecting the profile values as platform secrets with `APP_ENV` set;
then no profile file needs to exist at all.

## The production gate

`enforce_production_settings()` runs at startup and raises `RuntimeError` listing every problem at once,
because a service that boots unconfigured in production is worse than one that refuses to boot.

It treats any `APP_ENV` value outside `dev`, `development`, `local`, `test` and `testing` as production —
so `APP_ENV=staging` is held to the production standard, deliberately. The checks are:

- `LLM_BACKEND` names a backend whose credentials are all present (the `llm_enabled` computed gate).

- `PG_DSN` is set.

## Adding a setting

Do all of these in one change, or the suite and the next reader will disagree with the code:

1. Add the field to `Settings` with an explicit alias:
   `new_var: str | None = Field(default=None, validation_alias="NEW_VAR")`. Use `SecretStr` if it is a
   credential.
2. Document it in `.env.example`.
3. Put a non-secret default in `.env.shared`, or a placeholder in `.env.test.example` and
   `.env.production.example` when it is secret or environment-specific.
4. Add `"NEW_VAR"` to `MANAGED_ENV_VARS` in `tests/conftest.py`, so a value exported in a developer's
   shell cannot leak into the test suite.
5. If the service must not run without it in production, add a check to `enforce_production_settings()`.
6. Add the row to the table above.
