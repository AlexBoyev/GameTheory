"""Named worlds, loaded from `config/presets/*.yaml` (SPEC section 12).

A preset is a set of overrides on top of `WorldConfig`'s defaults, not a
separate schema - so a preset can only ever say things the config can already
express, and a typo in a file is a validation error rather than a silently
ignored key.

The catalogue is read from the files themselves. Hard-coding names and
descriptions here as well would mean two places to change and one of them
eventually lying.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from app.core.world_config import WorldConfig

LOG = structlog.get_logger(__name__)

PRESET_DIRNAME = "presets"

DESCRIPTIONS: Mapping[str, str] = {
    "peaceful_eden": "Abundant food, cooperative strategy mix - watch trust accumulate.",
    "harsh_winter": "Scarcity high, starts in winter - cooperation under hunger.",
    "liars_island": "Low honesty, high cunning - gossip and deception dominate.",
    "tribal_wars": "Four tribes already formed on contested ground - raids and treaties.",
    "axelrod_tournament": "Survival off: strategies meet, and the mix drifts to what scores.",
    "llm_schemers": "A handful of deliberative minds among reactive ones - they plot out loud.",
}
"""One-line summaries for the UI, by preset id.

In code rather than in the YAML because they are interface copy, not world
configuration: changing one must not invalidate a saved world.
"""


@dataclass(frozen=True, slots=True)
class Preset:
    """One named world: what to call it, and what it changes."""

    id: str
    name: str
    description: str
    overrides: dict[str, Any]

    def apply_to(self, base: WorldConfig) -> WorldConfig:
        """Return `base` with this preset's overrides applied.

        The seed is deliberately *not* overridden: picking a preset should not
        silently throw away a seed the user typed in next to it.
        """
        return base.model_copy(update=self.overrides, deep=True)


def preset_dir(config_dir: Path) -> Path:
    """Where the preset files live."""
    return config_dir / PRESET_DIRNAME


def _read(path: Path) -> dict[str, Any]:
    """Load one preset file into a plain mapping."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def load_preset(preset_id: str, config_dir: Path) -> Preset | None:
    """Load one preset by id, or None if there is no such file.

    An override the config cannot accept is a hard error: a preset that
    silently did nothing would be far worse than one that refuses to load.
    """
    path = preset_dir(config_dir) / f"{preset_id}.yaml"
    if not path.is_file():
        return None

    raw = _read(path)
    name = str(raw.pop("name", preset_id.replace("_", " ").title()))
    try:
        # Validate the overrides against the real schema before anyone builds
        # a world from them, so the error names the file and not the engine.
        WorldConfig.model_validate(WorldConfig().model_dump() | raw)
    except ValidationError as error:
        msg = f"preset {path.name} is not a valid WorldConfig override: {error}"
        raise ValueError(msg) from error

    return Preset(
        id=preset_id,
        name=name,
        description=DESCRIPTIONS.get(preset_id, ""),
        overrides=raw,
    )


def load_presets(config_dir: Path) -> list[Preset]:
    """Load every preset file, newest schema first, skipping broken ones.

    One unreadable file must not take the catalogue (and so the New World
    dialog) down with it, so a failure is logged and that entry omitted.
    """
    directory = preset_dir(config_dir)
    if not directory.is_dir():
        return []

    presets: list[Preset] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            preset = load_preset(path.stem, config_dir)
        except ValueError as error:
            LOG.warning("preset.invalid", preset=path.stem, error=str(error))
            continue
        if preset is not None:
            presets.append(preset)
    return presets
