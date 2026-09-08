# Agentic Petstore - project status

This is the Agentic Petstore onboarding project: a conversational, LLM-driven
shopping assistant for a pet store, built on top of a supplied FastAPI +
PostgreSQL Petstore application. The implementation follows the step-by-step
journey in [`petstore-api/ONBOARDING.md`](petstore-api/ONBOARDING.md) section
12, which governs the whole project.

## What was provided vs. what was built

**Provided:** a working FastAPI + PostgreSQL Petstore application
(`petstore-api`) - pet inventory, availability, and orders, with a
`/pets`/`/pets/{id}`/order-style HTTP API and a seeded inventory. Framework
documentation, AES documentation, and a reference project were also supplied
(not part of this repository).

**Built**, as five UV-managed Python 3.14 projects:

- **`petstore-api`** (given, lightly extended) - the sole owner of Petstore
  data. Pydantic models (`app/schemas.py`) enforce the domain rules below at
  the API boundary; `app/crud.py` enforces the sold-pet restriction.
- **`pet-client`** - the one application boundary that talks to
  petstore-api's HTTP API. Turns raw HTTP responses into typed
  pet/search/purchase results and clear failure outcomes (not found, already
  sold, invalid request, store unavailable, purchase unsuccessful).
- **`pet-mcp`** - an MCP server exposing exactly three tools:
  `pet_mcp_search_pets`, `pet_mcp_get_pet`, `pet_mcp_purchase_pet` (the last
  gated behind an explicit `confirm=True`, raising a `CONFIRMATION_REQUIRED`
  tool error otherwise). Talks to petstore-api only through `pet-client`.
- **`pet-aes`** - generic Agentic Enterprise System building blocks
  (`AgentSpec`, `build_agent`, `HostedAgentService`) that this project's agent
  is hosted in. Filters whatever tools an MCP server exposes down to an
  explicit per-agent allow-list, so pet-mcp exposing more tools later can
  never silently grant the agent more capability.
- **`pet-agent`** - the Petstore shopping assistant itself: a Pydantic AI
  agent (`agent.py`) wired to pet-mcp's three tools through pet-aes, and an
  interactive command-line dialogue (`cli.py`) that talks to it exclusively
  through `pet_aes.HostedAgentService` - the CLI never builds or calls the
  agent directly, and never imports pet-mcp/pet-client/a database driver.

## How the system fits together

```
CLI  -->  AES (HostedAgentService)  -->  Pydantic AI agent  -->  Litellm/LLM
                                              |
                                              v (MCP, stdio)
                                          pet-mcp
                                              |
                                              v
                                         pet-client
                                              |
                                              v (HTTP)
                                        petstore-api  -->  PostgreSQL
```

The agent never talks to petstore-api, pet-client, or the database directly -
every Petstore action goes through pet-mcp's three tools. The CLI never talks
to the agent directly - every message goes through AES's
`HostedAgentService`. petstore-api is the only component that reads or
writes the database directly.

pet-agent and pet-mcp are bundled into one Docker container (pet-agent
launches pet-mcp as a stdio subprocess, exactly as it does outside Docker);
petstore-api and its PostgreSQL database run as two more containers. See
`pet-agent/Dockerfile` for the full reasoning behind the combined image.

## Which customer actions are supported

Built up gradually per Step 6, and exposed through the CLI per Step 8:

1. List the pets currently available.
2. Filter pets by species, price, or other stated characteristics.
3. Show the details of a specific pet, including from a follow-up reference
   ("tell me more about the first one", "how much is it").
4. Prepare a purchase for a chosen pet.
5. Confirm and place the purchase, only after the customer has explicitly
   confirmed.
6. Explain a failure honestly (pet not found, already sold, store
   unavailable) without inventing an order number or receipt.
7. Continue browsing or exit the conversation at any point (typing
   `exit`/`quit`/`bye`, or Ctrl-D).

The CLI shows only the assistant's own reply text - never raw model output,
internal tool call details, validation traces, API response bodies, or
secrets.

## Main pet validation rules

Enforced by Pydantic models in `petstore-api/app/schemas.py`, so invalid data
is rejected without ever involving the LLM:

- `name`: 2-50 characters.
- `species`: one of `dog`, `cat`, `rabbit`, `bird`, `reptile`, `other`
  (`other` requires `specific_species` to be set).
- `age_months`: >= 0.
- `weight_kg`: > 0.
- `tail_length_cm`: >= 1.
- `price_eur`: > 0.
- `description`: 10-500 characters.
- `photo_references`: at least one.
- `tags`: no blank or duplicate tags.
- `availability`: one of `available`, `pending`, `sold`.

## Purchase-confirmation rule

A purchase only proceeds once the customer has explicitly confirmed it -
enforced at the pet-mcp layer (`pet_mcp_purchase_pet` requires
`confirm=True`, and raises a `CONFIRMATION_REQUIRED` error otherwise) and
surfaced by the CLI as an explicit yes/no step (Step 8, items 6-7) before any
order is placed. petstore-api independently refuses to sell a pet whose
`availability` is not `available` (the sold-pet restriction), so a
double-purchase or a stale offer cannot succeed even if the agent's own state
were wrong.

## Starting and stopping the complete environment

```bash
cp .env.example .env
# edit .env: fill in your real LLM_BACKEND/OPENAI_BASE_URL/OPENAI_API_KEY/LLM_MODEL

docker compose up -d --build db petstore-api   # database + Petstore API, in the background
docker compose run --rm pet-agent              # the CLI - an interactive conversation
```

petstore-api becomes available at http://localhost:8000 (interactive docs at
`/docs`). `docker compose run --rm pet-agent` (not `up`) attaches your real
terminal to the CLI and removes the container once you exit; run it again any
time for a new conversation against the same running database and API.

```bash
docker compose stop                    # stop everything; the database volume is untouched
docker compose up -d db petstore-api   # start again - same data, purchases and availability intact
```

Purchases and availability changes persist across restarts (verified): they
live in the `petstore-db-data` named volume, not in the containers
themselves. Only `docker compose down -v` or an explicit `docker volume rm`
erases it.

## Running project checks

Each of the five projects is UV-managed and carries the same Makefile
targets:

```bash
make check   # uv lock --locked, pre-commit/ruff, mypy --strict, deptry
make test    # pytest --cov
```

`pet-agent` additionally has an offline test suite covering the CLI dialogue
loop (`tests/test_cli.py`), the agent's tool-allow-list enforcement and
wiring (`tests/test_agent.py`, using an in-process fake MCP server and
`TestModel` - no network, no real LLM), and a manual, real-service script
(`verify_agent_conversation.py`) that exercises the seven Step 6 behaviors
against the real stack for a human to read back against ONBOARDING.md
sections 9-10.

## Known deviation from ONBOARDING.md

Step 5 specifies accessing the language model through Litellm. This
implementation instead connects directly to OpenRouter using the
OpenAI-compatible backend (`LLM_BACKEND=openai_compat`,
`OPENAI_BASE_URL=https://openrouter.ai/api/v1`) - a deviation carried from
earlier in the project, not yet reconciled with a Litellm proxy. The
credential-handling requirement itself is met either way: the key is never
committed, never baked into a Docker image, and is only ever supplied to the
running process at runtime (see `.env.example` and `.dockerignore`).

## Known limitations / not yet done

- **Step 11** (full end-to-end journey verification) has been substantively
  exercised (the full CLI -> AES -> agent -> MCP -> client -> API -> DB chain
  works live, and a purchase/availability change surviving a restart has
  been confirmed live), but is not yet formally complete: the two scripts
  above (`verify_domain_rules.py`, `verify_section13.py`) still need to be
  run against the real Docker stack and their output reviewed, e.g.:

  ```bash
  docker compose run --rm -T pet-agent python3 verify_domain_rules.py
  docker compose run --rm -T pet-agent uv run python verify_section13.py
  ```

  along with three one-off scenarios that need a deliberately broken
  environment rather than a script (missing Litellm/LLM key, petstore-api
  unavailable, pet-mcp unavailable).
- `pet-mcp`'s own standalone `Dockerfile`/`docker-compose*.yml` are unused by
  the current architecture (pet-mcp is bundled into the pet-agent image
  instead of deployed as its own container) and have not been kept
  independently correct.
- The formal deliverables in ONBOARDING.md section 18 (architecture diagram,
  domain rule overview as a standalone document, verification evidence,
  example conversations for a successful/cancelled/failed journey) have not
  been assembled as a dedicated package yet - most of the underlying content
  already exists in this README and in each project's own tests/README, but
  it has not been organized to match section 18's structure.
