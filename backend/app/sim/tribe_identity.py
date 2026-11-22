"""What a tribe is called and what colour it is drawn in.

Lives in `sim/` because a `Tribe` is a `sim/` entity: world generation needs
to name the tribes a preset starts with, and `sim/` may not import `ai/`.
"""

TRIBE_COLOURS: tuple[str, ...] = (
    "#e8a6a6",
    "#a6c8e8",
    "#b6e0a6",
    "#e8d2a6",
    "#c9a6e8",
    "#a6e8d8",
    "#e8bda6",
    "#bfbfe8",
)

_TRIBE_FIRST = ("Ash", "Bay", "Cliff", "Dune", "Elm", "Fen", "Glen", "Holt")
_TRIBE_SECOND = ("folk", "kin", "clan", "band", "hearth", "circle")


def tribe_name(tribe_id: int) -> str:
    """A readable name, unique per tribe id.

    Derived from the id alone rather than hashed, so two tribes can never
    end up both called Holtclan - which they did, three times, before this.
    """
    first = _TRIBE_FIRST[tribe_id % len(_TRIBE_FIRST)]
    second = _TRIBE_SECOND[(tribe_id // len(_TRIBE_FIRST)) % len(_TRIBE_SECOND)]
    cycle = tribe_id // (len(_TRIBE_FIRST) * len(_TRIBE_SECOND))
    suffix = "" if cycle == 0 else f" {cycle + 1}"
    return f"{first}{second}{suffix}"
