from typing import Any

from app import schemas
from app.database import Connection, PetRow


class PetNotFoundError(Exception):
    pass


class PetNotAvailableError(Exception):
    pass


def list_pets(conn: Connection, search: schemas.PetSearch) -> list[PetRow]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if search.species is not None:
        conditions.append("species = %(species)s")
        params["species"] = search.species.value
    if search.breed is not None:
        conditions.append("breed ILIKE %(breed)s")
        params["breed"] = search.breed
    if search.min_age_months is not None:
        conditions.append("age_months >= %(min_age_months)s")
        params["min_age_months"] = search.min_age_months
    if search.max_age_months is not None:
        conditions.append("age_months <= %(max_age_months)s")
        params["max_age_months"] = search.max_age_months
    if search.min_price_eur is not None:
        conditions.append("price_eur >= %(min_price_eur)s")
        params["min_price_eur"] = search.min_price_eur
    if search.max_price_eur is not None:
        conditions.append("price_eur <= %(max_price_eur)s")
        params["max_price_eur"] = search.max_price_eur
    if search.availability is not None:
        conditions.append("availability = %(availability)s")
        params["availability"] = search.availability.value
    if search.name_contains is not None:
        conditions.append("name ILIKE %(name_contains)s")
        params["name_contains"] = f"%{search.name_contains}%"
    if search.tags:
        conditions.append("tags && %(tags)s")
        params["tags"] = [tag.strip().lower() for tag in search.tags]

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM pets {where_clause} ORDER BY id"  # noqa: S608 (identifiers are static, values are parameterized)

    return conn.execute(query, params).fetchall()


def get_pet(conn: Connection, pet_id: int) -> PetRow:
    pet = conn.execute("SELECT * FROM pets WHERE id = %(id)s", {"id": pet_id}).fetchone()
    if pet is None:
        raise PetNotFoundError(f"Pet {pet_id} was not found.")
    return pet


def create_pet(conn: Connection, pet_in: schemas.PetCreate) -> PetRow:
    data = pet_in.model_dump()
    data["species"] = data["species"].value
    data["availability"] = data["availability"].value

    columns = list(data.keys())
    placeholders = ", ".join(f"%({col})s" for col in columns)
    column_list = ", ".join(columns)

    row = conn.execute(
        f"INSERT INTO pets ({column_list}) VALUES ({placeholders}) RETURNING *",  # noqa: S608
        data,
    ).fetchone()
    assert row is not None
    return row


def purchase_pet(conn: Connection, pet_id: int) -> PetRow:
    pet = get_pet(conn, pet_id)
    if pet["availability"] != "available":
        raise PetNotAvailableError(f"Pet {pet_id} is not available for purchase.")

    order = conn.execute(
        "INSERT INTO orders (pet_id, price_eur) VALUES (%(pet_id)s, %(price_eur)s) RETURNING *",
        {"pet_id": pet_id, "price_eur": pet["price_eur"]},
    ).fetchone()
    assert order is not None

    conn.execute(
        "UPDATE pets SET availability = 'sold' WHERE id = %(id)s",
        {"id": pet_id},
    )
    return order
