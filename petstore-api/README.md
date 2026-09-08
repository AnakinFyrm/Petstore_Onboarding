# Petstore API

A beginner FastAPI Petstore application. It is the store's source of truth for
pet inventory, availability, and orders, and is meant to be used as the
starting point for the Agentic Petstore onboarding project.

## What this is

- A FastAPI application backed by PostgreSQL 19 (beta).
- Plain SQL through `psycopg` (no ORM).
- Python 3.14, managed with `uv`, type-checked with `mypy --strict`.
- A multi-stage Dockerfile: dependencies and bytecode are compiled in a `uv`
  builder stage, and the runtime image only carries the built virtual
  environment and application code, running as a non-root user.
- Pydantic models that validate pet, search, and purchase data.
- A seeded inventory covering the required onboarding scenarios (multiple
  species, ages, prices, tags, a pending pet, a sold pet, and a pet with a
  tail length of exactly 1 cm).

## Run it

```bash
docker compose up --build
```

The API is then available at http://localhost:8000. Interactive docs are at
http://localhost:8000/docs.

Stop it with:

```bash
docker compose down
```

Data persists in a Docker volume, so pets and orders survive a restart. To
reset the database, remove the volume:

```bash
docker compose down -v
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check. |
| GET | `/pets` | List or search pets (species, breed, age range, price range, availability, tags, name). |
| GET | `/pets/{id}` | Retrieve one pet's details. |
| POST | `/pets` | Create a pet (used for seeding and testing). |
| POST | `/pets/{id}/purchase` | Buy an available pet. Fails if the pet is not available. |

The price used for a purchase always comes from the stored pet record, never
from the request body.

## Local development without Docker

```bash
uv sync
export DATABASE_URL=postgresql://petstore:petstore@localhost:5432/petstore
uv run uvicorn app.main:app --reload
```

This requires a PostgreSQL instance reachable at `DATABASE_URL`.

## Type checking

```bash
uv run mypy app
```

## Project structure

```
app/
  main.py       FastAPI routes
  crud.py       SQL queries against the pets/orders tables
  database.py   Connection handling and schema creation
  schemas.py    Pydantic request/response models and validation rules
  models.py     Species and availability enums
  seed.py       Starter inventory
```
