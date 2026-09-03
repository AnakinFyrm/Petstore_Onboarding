from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Availability, Species


class PetBase(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    species: Species
    specific_species: str | None = None
    breed: str | None = None
    age_months: int = Field(ge=0)
    weight_kg: float = Field(gt=0)
    tail_length_cm: float = Field(ge=1)
    description: str = Field(min_length=10, max_length=500)
    price_eur: float = Field(gt=0)
    availability: Availability = Availability.available
    tags: list[str] = Field(default_factory=list)
    photo_references: list[str] = Field(min_length=1)

    @field_validator("name", "breed", "description", "specific_species", mode="before")
    @classmethod
    def strip_whitespace(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("breed")
    @classmethod
    def breed_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("Breed may not be blank when provided.")
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for tag in tags:
            cleaned = tag.strip()
            if not cleaned:
                raise ValueError("Tags may not be blank.")
            key = cleaned.lower()
            if key in seen:
                raise ValueError(f"Duplicate tag: {cleaned}")
            seen[key] = cleaned
        return list(seen.values())

    @model_validator(mode="after")
    def species_requires_specific_species(self) -> "PetBase":
        if self.species == Species.other and not self.specific_species:
            raise ValueError("A specific species is required when species is 'other'.")
        return self


class PetCreate(PetBase):
    pass


class Pet(PetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PetSearch(BaseModel):
    species: Species | None = None
    breed: str | None = None
    min_age_months: int | None = Field(default=None, ge=0)
    max_age_months: int | None = Field(default=None, ge=0)
    min_price_eur: float | None = Field(default=None, gt=0)
    max_price_eur: float | None = Field(default=None, gt=0)
    availability: Availability | None = None
    tags: list[str] | None = None
    name_contains: str | None = None

    @field_validator("name_contains", mode="before")
    @classmethod
    def blank_name_is_no_filter(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def age_and_price_ranges_are_consistent(self) -> "PetSearch":
        if (
            self.min_age_months is not None
            and self.max_age_months is not None
            and self.min_age_months > self.max_age_months
        ):
            raise ValueError("Minimum age may not be greater than maximum age.")
        if (
            self.min_price_eur is not None
            and self.max_price_eur is not None
            and self.min_price_eur > self.max_price_eur
        ):
            raise ValueError("Minimum price may not be greater than maximum price.")
        return self


class PurchaseRequest(BaseModel):
    pet_id: int = Field(gt=0)


class Order(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    price_eur: float
