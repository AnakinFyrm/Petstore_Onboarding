from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import settings

PetRow = dict[str, Any]
Connection = psycopg.Connection[PetRow]

CREATE_TABLES = """
DO $$ BEGIN
    CREATE TYPE species AS ENUM ('dog', 'cat', 'rabbit', 'bird', 'reptile', 'other');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE availability AS ENUM ('available', 'pending', 'sold');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS pets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    species species NOT NULL,
    specific_species VARCHAR(50),
    breed VARCHAR(50),
    age_months INTEGER NOT NULL,
    weight_kg NUMERIC(6, 2) NOT NULL,
    tail_length_cm NUMERIC(6, 2) NOT NULL,
    description TEXT NOT NULL,
    price_eur NUMERIC(10, 2) NOT NULL,
    availability availability NOT NULL DEFAULT 'available',
    tags TEXT[] NOT NULL DEFAULT '{}',
    photo_references TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    pet_id INTEGER NOT NULL REFERENCES pets(id),
    price_eur NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def get_connection() -> Connection:
    return psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=False)


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(CREATE_TABLES)
        conn.commit()


@contextmanager
def db_session() -> Iterator[Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db() -> Iterator[Connection]:
    with db_session() as conn:
        yield conn
