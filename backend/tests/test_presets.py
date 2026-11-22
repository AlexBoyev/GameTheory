"""Named worlds (SPEC section 12).

A preset is overrides on top of `WorldConfig`, which is the whole point: it
can only say things the config can already express, so a typo is a loud
validation error rather than a setting that silently does nothing.
"""

from pathlib import Path

import pytest

from app.core.presets import DESCRIPTIONS, load_preset, load_presets
from app.core.world_config import WorldConfig

CONFIG_DIR = Path("config")

EXPECTED = {
    "peaceful_eden",
    "harsh_winter",
    "liars_island",
    "tribal_wars",
    "axelrod_tournament",
    "llm_schemers",
}


def test_every_documented_preset_exists_and_loads() -> None:
    """The six presets the SPEC and the README promise."""
    found = {preset.id for preset in load_presets(CONFIG_DIR)}

    assert found >= EXPECTED, EXPECTED - found


def test_every_preset_has_a_name_and_a_description() -> None:
    for preset in load_presets(CONFIG_DIR):
        assert preset.name and preset.name != preset.id, preset.id
        assert preset.description, f"{preset.id} has nothing to tell the user"


def test_descriptions_cover_exactly_the_presets_on_disk() -> None:
    """A description for a preset that no longer exists is a stale promise."""
    on_disk = {preset.id for preset in load_presets(CONFIG_DIR)}

    assert set(DESCRIPTIONS) == on_disk


def test_an_unknown_preset_is_none_not_an_error() -> None:
    assert load_preset("does_not_exist", CONFIG_DIR) is None


def test_every_preset_actually_changes_something() -> None:
    base = WorldConfig()

    for preset in load_presets(CONFIG_DIR):
        applied = preset.apply_to(base)
        assert applied != base, f"{preset.id} is a no-op"


def test_a_preset_never_overrides_the_seed() -> None:
    """Choosing a preset must not throw away a seed typed in beside it."""
    base = WorldConfig(seed=99)

    for preset in load_presets(CONFIG_DIR):
        assert preset.apply_to(base).seed == 99, preset.id


def test_a_preset_applies_on_top_of_a_given_config() -> None:
    """Tribal Wars, but with 400 agents, has to be one request."""
    preset = load_preset("tribal_wars", CONFIG_DIR)
    assert preset is not None

    applied = preset.apply_to(WorldConfig(max_agents=500))

    assert applied.max_agents == 500, "the base config survives"
    assert applied.initial_tribes == 4, "the preset still applies"


@pytest.mark.parametrize(
    ("preset_id", "field", "expected"),
    [
        ("peaceful_eden", "scarcity", 0.6),
        ("harsh_winter", "season_start", "winter"),
        ("harsh_winter", "scarcity", 2.2),
        ("tribal_wars", "initial_tribes", 4),
        ("axelrod_tournament", "tournament_mode", True),
        ("axelrod_tournament", "trembling_hand", 0.0),
        ("llm_schemers", "llm_agents", 6),
    ],
)
def test_the_presets_say_what_they_claim(preset_id: str, field: str, expected: object) -> None:
    preset = load_preset(preset_id, CONFIG_DIR)
    assert preset is not None

    assert getattr(preset.apply_to(WorldConfig()), field) == expected


def test_a_broken_preset_does_not_take_the_catalogue_down(tmp_path: Path) -> None:
    """One bad file must not empty the New World dialog."""
    directory = tmp_path / "presets"
    directory.mkdir()
    (directory / "good.yaml").write_text("name: Good\nscarcity: 1.5\n", encoding="utf-8")
    (directory / "broken.yaml").write_text("name: Broken\nscarcity: nonsense\n", encoding="utf-8")

    loaded = load_presets(tmp_path)

    assert [preset.id for preset in loaded] == ["good"]


def test_a_broken_preset_asked_for_by_name_is_a_loud_error(tmp_path: Path) -> None:
    """Silently ignoring it would be far worse than refusing to load it."""
    directory = tmp_path / "presets"
    directory.mkdir()
    (directory / "broken.yaml").write_text("population: -5\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"broken\.yaml"):
        load_preset("broken", tmp_path)


def test_an_unknown_field_is_rejected(tmp_path: Path) -> None:
    """`WorldConfig` forbids extras, so a typo cannot pass for a setting."""
    directory = tmp_path / "presets"
    directory.mkdir()
    (directory / "typo.yaml").write_text("scarcety: 2.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"typo\.yaml"):
        load_preset("typo", tmp_path)


def test_a_missing_preset_directory_is_an_empty_catalogue(tmp_path: Path) -> None:
    assert load_presets(tmp_path / "nowhere") == []
