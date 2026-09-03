# Operations

Runbook for `pet-agent`: how it ships, how to tell whether it is healthy, and what to check
first when it is not.

## Deploying

An MCP client owns the lifecycle: it starts the server as a subprocess and speaks the protocol over
stdio, so there is no listening port and nothing to keep running between sessions. A client entry looks
like `uv run pet-agent` with the working directory set to this checkout, or
`docker run --rm -i ghcr.io/fyrm-ai/pet-agent:X.Y.Z` for a pinned image.

The generated compose files assume a long-running networked service: a stdio server started detached has
no client attached to its stdin, so treat them as scaffolding for the day this server gains an HTTP
transport rather than as the way to run it.

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

The deploy `.env` holds **only** compose interpolation variables (`VERSION`) — application configuration goes in `.env.shared` and
`.env.$APP_ENV`, which every service loads through `env_file:`.

## Health and readiness

There is no HTTP surface. Liveness is the stdio connection itself: the client notices immediately when
the process exits. To check a build by hand, run `uv run pet-agent` and confirm it stays up
waiting for input; a startup failure prints to stderr and exits.

## When it looks unhealthy

Work down this list in order; each step is cheap and rules out a whole class of cause.

1. **Read the logs first** with `docker compose logs --tail=200 app`. Startup failures are loud and specific; there is no silent failure mode at boot.
1. **Did something write to stdout?** Under the stdio transport stdout carries the protocol framing, so a stray `print()` anywhere in a tool path corrupts the session and the client reports a parse error rather than a tool failure. Send diagnostics to stderr.
1. **Is the container restarting in a loop?** `docker compose ps` shows the restart count and the health state. `restart: unless-stopped` will retry a misconfigured process forever, so a short log tail can simply be the newest attempt.

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

Stdlib logging stays the source of truth during an incident (Logfire's own console output is off, because
this project's handler owns stdout). Sensitive values are scrubbed by name (`dsn`, `signing`, `api_key`,
`secret`) on top of Logfire's defaults; extend `SCRUB_PATTERNS` rather than trusting call sites, and keep
secrets and personal data out of span names and attributes.

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
