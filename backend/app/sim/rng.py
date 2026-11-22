"""Seeded randomness. The simulation never touches the global RNG.

Every subsystem gets its own named substream so adding a consumer cannot shift
the number stream of an existing one - that is what keeps replays identical.
"""

from zlib import crc32

import numpy as np


def derive_generator(seed: int, stream: str) -> np.random.Generator:
    """Return an independent generator for the named `stream`.

    The stream name is hashed with CRC32 (stable across processes and Python
    versions, unlike `hash()`), so `derive_generator(7, "worldgen")` always
    yields the same sequence.
    """
    entropy = crc32(stream.encode("utf-8"))
    return np.random.default_rng(np.random.SeedSequence([seed, entropy]))


def spawn_generators(seed: int, streams: tuple[str, ...]) -> dict[str, np.random.Generator]:
    """Return one named generator per entry in `streams`."""
    return {stream: derive_generator(seed, stream) for stream in streams}
