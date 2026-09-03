from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app import crud, schemas
from app.database import Connection, PetRow, get_db, init_db
from app.models import Availability, Species
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(init_db)
    await run_in_threadpool(seed_if_empty)
    yield


app = FastAPI(
    title="Petstore API",
    description="Beginner FastAPI Petstore application. Source of truth for pets, availability, and orders.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/pets", response_model=list[schemas.Pet])
def search_pets(
    species: Species | None = None,
    breed: str | None = None,
    min_age_months: int | None = Query(default=None, ge=0),
    max_age_months: int | None = Query(default=None, ge=0),
    min_price_eur: float | None = Query(default=None, gt=0),
    max_price_eur: float | None = Query(default=None, gt=0),
    availability: Availability | None = None,
    tags: list[str] | None = Query(default=None),
    name_contains: str | None = None,
    conn: Connection = Depends(get_db),
) -> list[PetRow]:
    try:
        search = schemas.PetSearch(
            species=species,
            breed=breed,
            min_age_months=min_age_months,
            max_age_months=max_age_months,
            min_price_eur=min_price_eur,
            max_price_eur=max_price_eur,
            availability=availability,
            tags=tags,
            name_contains=name_contains,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return crud.list_pets(conn, search)


@app.get("/pets/{pet_id}", response_model=schemas.Pet)
def get_pet(pet_id: int, conn: Connection = Depends(get_db)) -> PetRow:
    try:
        return crud.get_pet(conn, pet_id)
    except crud.PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/pets", response_model=schemas.Pet, status_code=201)
def create_pet(pet_in: schemas.PetCreate, conn: Connection = Depends(get_db)) -> PetRow:
    return crud.create_pet(conn, pet_in)


@app.post("/pets/{pet_id}/purchase", response_model=schemas.Order, status_code=201)
def purchase_pet(pet_id: int, conn: Connection = Depends(get_db)) -> PetRow:
    try:
        return crud.purchase_pet(conn, pet_id)
    except crud.PetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except crud.PetNotAvailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
