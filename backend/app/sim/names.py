"""Deterministic agent names.

Names come from the seeded RNG, never from `random`, so the same seed always
produces the same cast of characters - which matters when you are trying to
tell someone "watch Rex, he betrays Juno on day 4".
"""

import numpy as np

_FIRST: tuple[str, ...] = (
    "Ada", "Bram", "Cira", "Dax", "Eda", "Finn", "Gwen", "Hal", "Ilma", "Jex",
    "Kai", "Lune", "Mira", "Nox", "Oda", "Pike", "Quil", "Rex", "Sable", "Tove",
    "Ulf", "Vena", "Wren", "Xan", "Yara", "Zeb", "Bo", "Cleo", "Dov", "Esk",
    "Fay", "Gus", "Hema", "Iro", "Juno", "Kesh", "Lira", "Mox", "Nell", "Orin",
)  # fmt: skip

_SUFFIX: tuple[str, ...] = (
    "", "", "", "", "-ka", "-mo", "-ti", "-sh", "-el", "-ra",
)  # fmt: skip


def make_name(rng: np.random.Generator, used: set[str]) -> str:
    """Return a name that is not already in `used`, and record it.

    Falls back to a numbered variant once the base names run out, so a world of
    500 agents still gets unique, readable names.
    """
    for _ in range(8):
        stem = _FIRST[int(rng.integers(len(_FIRST)))]
        suffix = _SUFFIX[int(rng.integers(len(_SUFFIX)))]
        candidate = f"{stem}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate

    stem = _FIRST[int(rng.integers(len(_FIRST)))]
    index = 2
    while f"{stem} {index}" in used:
        index += 1
    candidate = f"{stem} {index}"
    used.add(candidate)
    return candidate
