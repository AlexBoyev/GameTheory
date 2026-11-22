"""Payoffs, consequences and the social bookkeeping of an encounter."""

from pathlib import Path

import numpy as np
import pytest

from app.ai.gametheory.encounters import GameKind, PayoffMatrix
from app.ai.gametheory.ledger import SocialLedger
from app.ai.gametheory.payoffs import load_payoffs
from app.ai.gametheory.resolver import EncounterResolver
from app.ai.gametheory.strategies import Move, build_strategy_registry
from app.ai.minds import MindRegistry
from app.sim.entities import Agent, ResourceKind
from app.sim.world import World
from tests.factories import centre_agent, clear_resources, place

C = Move.COOPERATE
D = Move.DEFECT


def resolver(minds: MindRegistry) -> EncounterResolver:
    """A resolver wired to the real payoff defaults."""
    return EncounterResolver(load_payoffs(), build_strategy_registry(), minds)


def pair(world: World) -> tuple[Agent, Agent]:
    """Two agents standing next to each other in the middle of the island."""
    first = centre_agent(world)
    agents = world.living_agents()
    second = next(a for a in agents if a.id != first.id)
    second.position = (1.0, 0.0)
    world.agent_index.insert(second.id, 1.0, 0.0)
    return first, second


# ------------------------------------------------------------------ payoffs


def test_payoff_matrix_follows_the_classic_table() -> None:
    matrix = PayoffMatrix(temptation=5.0, reward=3.0, punishment=1.0, sucker=0.0)

    assert matrix.payoff(C, C) == 3.0
    assert matrix.payoff(D, C) == 5.0
    assert matrix.payoff(C, D) == 0.0
    assert matrix.payoff(D, D) == 1.0
    assert matrix.is_dilemma


def test_a_matrix_that_is_not_a_dilemma_is_rejected(tmp_path: Path) -> None:
    from pathlib import Path

    path = Path(str(tmp_path)) / "payoffs.yaml"
    path.write_text(
        "prisoners_dilemma:\n  temptation: 1.0\n  reward: 5.0\n  punishment: 2.0\n  sucker: 0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="T > R > P > S"):
        load_payoffs(path)


def test_the_shipped_payoffs_load_and_are_a_dilemma() -> None:
    from pathlib import Path

    config = load_payoffs(Path("config/payoffs.yaml"))

    assert config.matrix(GameKind.PRISONERS_DILEMMA).is_dilemma
    assert config.matrix(GameKind.STAG_HUNT).reward > config.matrix(GameKind.STAG_HUNT).temptation
    assert config.matrix(GameKind.HAWK_DOVE).punishment < 0, "two hawks must both suffer"
    assert 0.0 <= config.trembling_hand <= 0.2


# ----------------------------------------------------------- game selection


def test_a_surplus_beside_a_hungry_neighbour_is_a_dilemma(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.inventory.food = 3.0
    second.needs.hunger = 20.0

    assert resolver(minds).pick_game(world, first, second) is GameKind.PRISONERS_DILEMMA


def test_two_hungry_agents_near_a_deer_play_a_stag_hunt(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    place(world, ResourceKind.DEER, (3.0, 0.0))
    first.needs.hunger = 20.0
    second.needs.hunger = 20.0
    first.inventory.food = 0.0
    second.inventory.food = 0.0

    assert resolver(minds).pick_game(world, first, second) is GameKind.STAG_HUNT


def test_two_agents_reaching_for_the_same_thing_play_hawk_dove(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.inventory.food = 0.0
    second.inventory.food = 0.0
    first.needs.hunger = 90.0
    second.needs.hunger = 90.0
    first.current_skill = "Gather"
    second.current_skill = "Gather"

    assert resolver(minds).pick_game(world, first, second) is GameKind.HAWK_DOVE


def test_a_passing_meeting_is_not_a_game(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.inventory.food = 0.0
    second.inventory.food = 0.0
    first.needs.hunger = 95.0
    second.needs.hunger = 95.0

    assert resolver(minds).pick_game(world, first, second) is None


# ------------------------------------------------------------ consequences


def test_sharing_moves_food_from_the_richer_to_the_poorer(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.strategy = "AlwaysCooperate"
    second.strategy = "AlwaysCooperate"
    first.inventory.food = 5.0
    second.inventory.food = 0.0
    second.needs.hunger = 20.0
    before = first.inventory.food + second.inventory.food

    result = resolver(minds).resolve(world, first, second)

    assert result is not None
    assert result.mutual_cooperation
    assert second.inventory.food > 0.0
    assert first.inventory.food + second.inventory.food == pytest.approx(before), (
        "food is transferred, never created"
    )


def test_defecting_on_a_sharer_takes_their_food(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.strategy = "AlwaysCooperate"
    second.strategy = "AlwaysDefect"
    first.inventory.food = 4.0
    second.inventory.food = 0.0
    second.needs.hunger = 20.0

    # Trembling hand off, so the moves are exactly the strategies'.
    config = load_payoffs()
    quiet = EncounterResolver(
        type(config)(matrices=config.matrices, trembling_hand=0.0),
        build_strategy_registry(),
        minds,
    )
    result = quiet.resolve(world, first, second)

    assert result is not None
    assert (result.move_a, result.move_b) == (C, D)
    assert second.inventory.food > 0.0
    assert first.inventory.food < 4.0


def test_an_encounter_updates_trust_on_both_sides(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.strategy = "AlwaysCooperate"
    second.strategy = "AlwaysCooperate"
    first.inventory.food = 4.0
    second.needs.hunger = 20.0

    resolver(minds).resolve(world, first, second)

    assert minds.require(first.id).memory.social[second.id].trust > 0
    assert minds.require(second.id).memory.social[first.id].trust > 0


def test_defecting_on_someone_who_trusted_you_is_a_betrayal(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.strategy = "AlwaysDefect"
    second.strategy = "AlwaysCooperate"
    first.inventory.food = 0.0
    second.inventory.food = 4.0
    first.needs.hunger = 20.0

    # Second already trusts first.
    minds.require(second.id).memory.relationship(first.id).trust = 0.8

    config = load_payoffs()
    quiet = EncounterResolver(
        type(config)(matrices=config.matrices, trembling_hand=0.0),
        build_strategy_registry(),
        minds,
    )
    result = quiet.resolve(world, first, second)

    assert result is not None
    assert first.id in result.betrayal_by
    assert minds.require(second.id).memory.social[first.id].trust < 0.8


def test_the_ledger_counts_what_happened(world: World) -> None:
    minds = MindRegistry()
    minds.sync(world)
    first, second = pair(world)
    clear_resources(world)
    first.strategy = "AlwaysCooperate"
    second.strategy = "AlwaysCooperate"
    first.inventory.food = 4.0
    second.needs.hunger = 20.0

    ledger = SocialLedger()
    result = resolver(minds).resolve(world, first, second)
    assert result is not None
    ledger.record_encounter(result, first.strategy, second.strategy)

    assert ledger.rounds[result.game.value] == 2
    assert 0.0 <= ledger.cooperation_rate() <= 1.0
    assert "AlwaysCooperate" in ledger.average_payoffs()


def test_resolution_is_deterministic_for_a_seed(world: World) -> None:
    def run(seed: int) -> tuple[str, str]:
        minds = MindRegistry()
        minds.sync(world)
        first, second = pair(world)
        clear_resources(world)
        first.strategy = "Random"
        second.strategy = "Random"
        first.inventory.food = 4.0
        second.needs.hunger = 20.0
        world.rngs["encounter"] = np.random.default_rng(seed)
        result = resolver(minds).resolve(world, first, second)
        assert result is not None
        return result.move_a.value, result.move_b.value

    assert run(7) == run(7)
