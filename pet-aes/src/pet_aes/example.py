"""Example module for pet-aes.

Replace this with the real code. It exists to show the shape the tooling
expects: typed signatures, docstrings that mkdocstrings can render, and small
pure functions that are cheap to test.
"""

from collections.abc import Iterable


def slugify(value: str) -> str:
    """Return a lowercase, hyphen-separated form of ``value``.

    Runs of non-alphanumeric characters collapse into a single hyphen, and
    leading and trailing hyphens are removed.

        >>> slugify("Jordex  Booking Ref!")
        'jordex-booking-ref'
    """
    pieces = ["".join(c for c in chunk if c.isalnum()) for chunk in value.lower().split()]
    return "-".join(piece for piece in pieces if piece)


def chunked[T](items: Iterable[T], size: int) -> list[list[T]]:
    """Split ``items`` into consecutive lists of at most ``size`` elements.

    Raises:
        ValueError: if ``size`` is not positive.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    batch: list[T] = []
    batches: list[list[T]] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)
    return batches
