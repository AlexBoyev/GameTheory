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


_SHADES: tuple[float, ...] = (0.0, -0.28, -0.48, -0.62)
"""How much to darken the base hue, one step per naming cycle.

Only darker, never lighter: the base palette is already pale, so lightening
a pastel moves it a few points towards white and two tribes still look the
same. These stay inside the soft palette the scene asks for.
"""


def _darken(channel: int, amount: float) -> int:
    """Move one 0-255 channel towards black by `amount` (0 leaves it alone)."""
    return round(channel * (1.0 + amount))


def tribe_colour(tribe_id: int) -> str:
    """A colour, unique per tribe id, in the same family as its name.

    `tribe_name` was made unique after three tribes ended up called
    Holtclan; the colour was left indexing an eight-entry palette, so
    Clifffolk and Cliffkin came out identically pale green - and colour is
    what the scene actually draws, on beans and on territory rings alike.

    Same stem, same hue; later naming cycles get a deeper shade of it, so
    Cliffkin reads as a darker Clifffolk rather than as a stranger.
    """
    base = TRIBE_COLOURS[tribe_id % len(TRIBE_COLOURS)]
    shade = _SHADES[(tribe_id // len(TRIBE_COLOURS)) % len(_SHADES)]
    channels = (int(base[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{_darken(channel, shade):02x}" for channel in channels)
