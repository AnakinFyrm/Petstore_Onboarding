"""Tests for the example module."""

import pytest

from pet_aes.example import chunked, slugify


def test_slugify_lowercases_and_joins() -> None:
    assert slugify("Jordex  Booking Ref!") == "jordex-booking-ref"


def test_slugify_drops_punctuation_only_words() -> None:
    assert slugify("a -- b") == "a-b"


def test_slugify_of_empty_string() -> None:
    assert slugify("   ") == ""


def test_chunked_splits_evenly() -> None:
    assert chunked([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_chunked_keeps_the_remainder() -> None:
    assert chunked([1, 2, 3], 2) == [[1, 2], [3]]


def test_chunked_of_empty_input() -> None:
    assert chunked([], 3) == []


def test_chunked_rejects_a_non_positive_size() -> None:
    with pytest.raises(ValueError, match="size must be positive"):
        chunked([1, 2], 0)
