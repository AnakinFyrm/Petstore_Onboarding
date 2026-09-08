import enum


class Species(str, enum.Enum):
    dog = "dog"
    cat = "cat"
    rabbit = "rabbit"
    bird = "bird"
    reptile = "reptile"
    other = "other"


class Availability(str, enum.Enum):
    available = "available"
    pending = "pending"
    sold = "sold"
