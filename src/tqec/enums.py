from enum import Enum, auto


class Orientation(Enum):
    """Either horizontal or vertical orientation."""

    HORIZONTAL = auto()
    VERTICAL = auto()


class Basis(Enum):
    X = "X"
    Z = "Z"
