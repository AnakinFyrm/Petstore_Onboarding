# Operations

Runbook for `pet-agent`: how it ships, how to tell whether it is healthy, and what to check
first when it is not.

## Deploying

### Container image

```bash
make docker-build                 # docker build -t pet-agent .
```

The build is two-stage: uv resolves and installs into `/app/.venv` in the builder, and the runtime stage
is a plain `python:3.14-slim-bookworm` with no uv and no build tooling. It runs as the
non-root `app` user, `PATH` points at `/app/.venv/bin`, `UV_NO_SYNC=1` stops a stray `uv run` from
re-syncing inside the container, and `CMD` is the `pet-agent` console script.

Private git dependencies need a token during the build, passed as a BuildKit secret so it never lands in
a layer (see [Private dependencies](private-dependencies.md)).

Running the image directly, with the same layering the application expects (later `--env-file` wins):

```bash
docker run --rm \
  -e APP_ENV=production \
  --env-file .env.shared --env-file .env.production \
  pet-agent
```

### Images published by CI

| Trigger | Tags |
|---|---|
| merge to `main` | `ghcr.io/fyrm-ai/pet-agent:dev` and `:sha-<commit>` |
| GitHub Release `vX.Y.Z` | `:X.Y.Z` and `:X.Y` |

The release job refuses to publish when the release tag does not match `version` in `pyproject.toml`.
Old `dev` images are pruned weekly. Staging may track `dev`; production pins an exact `X.Y.Z` so a
rollback is a one-line change. Pulling needs `docker login ghcr.io` with a token that has
`read:packages`.

### Local stack

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
docker compose down
```

Postgres comes up alongside the app with throwaway local credentials and `init.sql` mounted into
`docker-entrypoint-initdb.d`, so a fresh volume is initialised with the schema.

### Production stack

`docker-compose.prod.yml` runs the published image instead of building from source:

```bash
docker login ghcr.io                                   # once per host
echo "VERSION=X.Y.Z" >> .env
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Upgrade by bumping `VERSION` and repeating the last two commands; roll back by setting the previous
version and doing the same. Never run `:latest` or `:dev` in production.

The deploy `.env` holds **only** compose interpolation variables (`VERSION`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`) — application configuration goes in `.env.shared` and
`.env.$APP_ENV`, which every service loads through `env_file:`.

## Health and readiness

The service is a one-shot CLI process: there is no endpoint to probe. The operational signals are the
exit status (`0` answered, `2` the LLM is not configured) and the log output. If you deploy it as a
long-running process, add a health surface first — copy the worker template's daemon-thread health
server rather than inventing one.

## When it looks unhealthy

Work down this list in order; each step is cheap and rules out a whole class of cause.

1. **Read the logs first** with `docker compose logs --tail=200 app`. Startup failures are loud and specific; there is no silent failure mode at boot.
1. **Did it refuse to start?** `RuntimeError: Refusing to start with APP_ENV='production': ...` is the fail-closed gate, and it lists *every* missing setting at once. Fix them all, then restart.
1. **Is `APP_ENV` what you think it is?** Anything outside `dev`, `development`, `local`, `test` and `testing` is treated as production. Check it in the running process, not in a file.
1. **Can the process see its env files?** They are read from the working directory only (`/app` in the image). A missing file is skipped silently, a key declared in both `.env.shared` and `.env.$APP_ENV` logs a `RuntimeWarning` naming the key, and the process environment overrides both.
1. **Ask the process what it resolved.** `make config-check` prints every setting with secrets masked, which settles most "the value is definitely set" arguments in one command. Inside the container: `docker compose exec app python -c "from pet_agent.config import get_settings; print(get_settings())"`.1. **Check the database.** Reachability first (`pg_isready -h <host> -U <user>`), then the DSN: a literal `%` in the password must be written `%25`, and an unencoded `@` or `/` silently changes which host or database is parsed out. Startup retries the first connection (`PG_CONNECT_ATTEMPTS`, backoff growing from `PG_CONNECT_BACKOFF_SECONDS`) and logs `Database not reachable (attempt n/m)` while it waits, so repeated warnings followed by `Could not connect to the database after N attempt(s)` means the DSN or the network is wrong, not that the database was merely slow. Requests that hang without an error usually mean the pool is exhausted (`PG_POOL_MAX_SIZE`) or a connection is held by a slow query. `apply_schema()` runs on every start, so a syntax error in `init.sql` fails the boot rather than degrading later.
1. **Is the LLM silently disabled?** `create_llm()` never raises: it logs `LLM backend ... unavailable` or `Unknown LLM_BACKEND` and returns `None`, and the CLI then exits `2` with `LLM not configured`. The `llm_enabled` gate needs the complete credential set for the selected backend, not just the key.
1. **Is the container restarting in a loop?** `docker compose ps` shows the restart count and the health state. `restart: unless-stopped` will retry a misconfigured process forever, so a short log tail can simply be the newest attempt.

## Logs and correlation ids

`setup_logging(level, log_format)` configures the root logger to stdout, and is idempotent.

- `LOG_FORMAT=text` (default): `%(asctime)s %(levelname)s %(name)s %(message)s`, one line per record.
- `LOG_FORMAT=json`: one JSON object per line with `timestamp`, `level`, `logger`, `message`, any
  `extra={...}` fields merged in, and `exception` when there is a traceback. Use this wherever a shipper
  or aggregator reads the logs.

Redaction is on by default (fyrm-service-core): secret-shaped keys (`authorization`, `api_key`,
`token`, `password`, ...) in `extra` fields and mapping arguments are replaced with `[redacted]`
before a record is emitted. Matching is exact and case-insensitive over key names — a secret
interpolated into the message string itself (`f"calling with {token}"`) is **not** caught, so keep
secrets out of message text. Extend the set with `setup_logging(redact_keys=["iban"])`; turning it
off (`redact=False`) is per-process and deliberately awkward.

A correlation id threads one unit of work through every record: it lives in a `ContextVar`, and
`CorrelationFilter` prefixes `correlation_id=<id>` onto each message and sets the record attribute — so in
JSON mode it is a top-level `correlation_id` field you can filter on.

Where the id comes from:

- The CLI sets `run-<random>` once per run, so the question, every tool call and every retry share one id.
- Any new entry point sets its own id the same way.

Finding everything for one id:

```bash
docker compose logs --no-log-prefix app | grep 'correlation_id=abc123'
docker compose logs --no-log-prefix app | jq -c 'select(.correlation_id == "abc123")'   # LOG_FORMAT=json
```

## Alerts

`alerting.py` is the seam for "a human must act and it will not fix itself". The default `LogAlerter`
writes `ALERT <severity>: <message>` with an `alert` field on the record, so a log-based rule is enough to
start with: match `ALERT` in text mode, or `select(.alert == true)` in JSON mode. Swap in a Teams, Slack
or PagerDuty implementation behind the same `Alerter` protocol without touching call sites.

Alerts are separate from logs and telemetry on purpose. If an alert fires routinely, it is the wrong
signal, and the fix is to remove it rather than to teach people to ignore it.

## Telemetry

Telemetry is **optional and fail-open**, which means an absent token is a normal state and not an error:

- No `LOGFIRE_TOKEN` (or `TELEMETRY_ENABLED=false`): `setup_telemetry()` configures nothing, logs a debug
  line, returns `False`, and nothing leaves the process. This is how tests and CI run.
- A token present and reachable: startup logs `Telemetry active (service=... environment=...)`, which is
  the one line to grep for when you want to know whether a deployment is reporting.
- A failure inside setup is logged (`Telemetry setup failed; continuing without it`) and swallowed.
  Telemetry never prevents the service from starting.

When traces are missing in an environment that should have them, check in this order: the startup line
above is absent (so the token is not in the *running* process environment — `make config-check` shows
what was resolved), then outbound HTTPS to the Logfire ingest endpoint, then whether the process lived
long enough for the exporter to flush.

Pydantic AI is instrumented natively, so agent runs, tool calls and token usage arrive as spans — the
fastest way to see where a run spent its requests and its tokens.

Stdlib logging stays the source of truth during an incident (Logfire's own console output is off, because
this project's handler owns stdout). Sensitive values are scrubbed by name (`dsn`, `signing`, `api_key`,
`secret`) on top of Logfire's defaults; extend `SCRUB_PATTERNS` rather than trusting call sites, and keep
secrets and personal data out of span names and attributes.

## Production settings are fail closed

`enforce_production_settings()` runs during startup and raises rather than booting with unsafe
configuration, listing every problem in one message. The exact checks for this project type, and the
full variable reference, are in [Configuration](configuration.md).

## Schema changes

`init.sql` is the schema of record and is applied on every start, so every statement is idempotent and
changes are additive (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`). There is no migration tool and no rollback machinery.

Dropping or retyping a column is not safe to run repeatedly against live data. Do it by hand,
deliberately, with a backup taken first:

```bash
pg_dump "$PG_DSN" > backup-$(date +%Y%m%d).sql
```

## CI and the release path

`main.yml` runs on every pull request and every push to `main`: the quality gate (`make check`), tests
plus `mypy` with a coverage upload to Codecov, and a strict docs build. Merges to
`main` also build and push the `dev` image.

Releasing:

1. Bump the version with `make bump`, which derives it from the conventional commits and updates
   `CHANGELOG.md` and the tag, and merge it to `main`.
2. Publish a GitHub Release tagged `vX.Y.Z`. `on-release-main.yml` then deploys the docs to GitHub Pages and publishes the versioned image after checking the tag against `pyproject.toml`.
3. On the host, set `VERSION=X.Y.Z` in the deploy `.env`, then
   `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d`.

## Supply-chain findings

`security.yml` runs weekly and on every pull request: `uv audit` over the locked dependency tree, zizmor
over the workflow definitions, and Trivy over the built image. Locally, `make audit` runs the dependency
half.

Everything is **report-only** — each scan step carries `continue-on-error: true`, so a newly published
advisory in a transitive dependency annotates the run instead of blocking an unrelated merge. Once this
repository's backlog is at zero, delete that line from a job to make it blocking. Nothing else changes.

Two things this does *not* do, which matter when you are deciding whether the repository is covered:

- **No source scanning beyond ruff's `S` rules.** CodeQL needs paid GitHub Code Security.
- **No alerts on advisories published against dependencies that have not changed** — that is what
  Dependabot alerts are for, and they are **off by default**. Turn them on once per repository in
  Settings > Advanced Security (alerts *and* security updates). They are free on the Team plan, and they
  are the part of this that arrives as a reviewable pull request rather than as an annotation nobody
  reads.
