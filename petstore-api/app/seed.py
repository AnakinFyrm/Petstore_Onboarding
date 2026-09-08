from app import crud, schemas
from app.database import db_session
from app.models import Availability, Species

SEED_PETS: list[schemas.PetCreate] = [
    schemas.PetCreate(
        name="Luna",
        species=Species.cat,
        breed="Domestic shorthair",
        age_months=24,
        weight_kg=4.1,
        tail_length_cm=27,
        description="Luna is a calm and friendly cat who enjoys sitting by the window.",
        price_eur=250,
        availability=Availability.available,
        tags=["calm", "friendly"],
        photo_references=["luna_01.jpg"],
    ),
    schemas.PetCreate(
        name="Milo",
        species=Species.cat,
        breed="Siamese",
        age_months=10,
        weight_kg=3.2,
        tail_length_cm=24,
        description="Milo is a playful young cat who loves chasing toys around the house.",
        price_eur=285,
        availability=Availability.available,
        tags=["playful", "young"],
        photo_references=["milo_01.jpg"],
    ),
    schemas.PetCreate(
        name="Max",
        species=Species.dog,
        breed="Labrador Retriever",
        age_months=36,
        weight_kg=28.5,
        tail_length_cm=45,
        description="Max is an active, well-trained dog who loves long walks outdoors.",
        price_eur=650,
        availability=Availability.available,
        tags=["active", "trained"],
        photo_references=["max_01.jpg"],
    ),
    schemas.PetCreate(
        name="Bella",
        species=Species.dog,
        breed="Golden Retriever",
        age_months=18,
        weight_kg=22.0,
        tail_length_cm=40,
        description="Bella is a gentle, family-friendly dog who gets along with children.",
        price_eur=720,
        availability=Availability.pending,
        tags=["gentle", "family-friendly"],
        photo_references=["bella_01.jpg"],
    ),
    schemas.PetCreate(
        name="Pip",
        species=Species.rabbit,
        breed="Dwarf rabbit",
        age_months=6,
        weight_kg=1.4,
        tail_length_cm=4,
        description="Pip is a small and quiet rabbit who enjoys nibbling on fresh vegetables.",
        price_eur=90,
        availability=Availability.available,
        tags=["small", "quiet"],
        photo_references=["pip_01.jpg"],
    ),
    schemas.PetCreate(
        name="Kiwi",
        species=Species.bird,
        breed="Budgerigar",
        age_months=8,
        weight_kg=0.05,
        tail_length_cm=8,
        description="Kiwi is a social and colourful bird who enjoys whistling at visitors.",
        price_eur=60,
        availability=Availability.available,
        tags=["social", "colourful"],
        photo_references=["kiwi_01.jpg"],
    ),
    schemas.PetCreate(
        name="Nova",
        species=Species.reptile,
        breed="Leopard gecko",
        age_months=14,
        weight_kg=0.06,
        tail_length_cm=12,
        description="Nova is a calm, low-noise reptile that is easy to care for.",
        price_eur=140,
        availability=Availability.sold,
        tags=["calm", "low-noise"],
        photo_references=["nova_01.jpg"],
    ),
    schemas.PetCreate(
        name="Sprout",
        species=Species.other,
        specific_species="Hedgehog",
        age_months=5,
        weight_kg=0.4,
        tail_length_cm=1,
        description="Sprout is a tiny hedgehog with the shortest tail in the whole store.",
        price_eur=110,
        availability=Availability.available,
        tags=["tiny", "quiet"],
        photo_references=["sprout_01.jpg"],
    ),
]


def seed_if_empty() -> None:
    with db_session() as conn:
        row = conn.execute("SELECT count(*) AS count FROM pets").fetchone()
        if row is not None and row["count"]:
            return
        for pet in SEED_PETS:
            crud.create_pet(conn, pet)
