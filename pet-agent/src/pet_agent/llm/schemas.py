"""Pydantic targets for LLM structured output.

Schemas here are deliberately loose: every field is optional and a string, so
the model is never forced to invent a value just to satisfy a type. This is
the loose-schema-then-strict-validation convention: the LLM fills in what it
actually found (missing values come back ``None``, never guessed), and strict
business validation (types, ranges, cross-field rules) happens afterwards in
ordinary code, where failures can be logged and handled instead of silently
shaping model output.
"""

from pydantic import BaseModel, Field


class ExtractedItem(BaseModel):
    """One item the model extracted from a document or instruction.

    All fields are optional strings by design; values must appear verbatim in
    the source. Replace this example with the schemas your agent needs, but
    keep the convention.
    """

    name: str | None = Field(None, description="The item's name exactly as written in the source")
    quantity: str | None = Field(None, description="Quantity as written, digits only, no unit")
    unit: str | None = Field(None, description="Unit as written (e.g. kg, pcs)")
    date: str | None = Field(None, description="Date as written, ISO YYYY-MM-DD when given")
    notes: str | None = Field(None, description="Free-text remarks copied from the source")
