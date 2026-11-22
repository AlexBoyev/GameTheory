"""Tournament mode (SPEC section 5.3).

The headline test is the last one: run the thing and check it reproduces
Axelrod's actual finding. The rest guard the properties that make that result
mean anything - survival really off, pairings exhaustive, scores per round
rather than per agent.
"""

import math
from collections import Counter
from pathlib import Path

import pytest

from app.ai.gametheory.encounters import GameKind
from app.ai.gametheory.ledger import SocialLedger
from app.ai.gametheory.payoffs import load_payoffs
from app.ai.gametheory.strategies import build_strategy_registry
from app.ai.minds import MindRegistry
from app.ai.systems.tournament_system import TournamentSystem
from app.core.presets import load_preset
from app.core.world_config import TerrainConfig, WorldConfig
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder
from app.sim.worldgen.arena import ring_positions
from tests.conftest import SMALL_TERRAIN

ARENA_TERRAIN = TerrainConfig(size=160.0, resolution=48)


def tournament_config(population: int = 18, **extra: object) -> WorldConfig:
    """A small tournament, so a test finishes a generation quickly."""
    return WorldConfig(
        seed=5,
        population=population,
        max_agents=population + 10,
        terrain=ARENA_TERRAIN,
        tournament_mode=True,
        **extra,  # type: ignore[arg-type]
    )


def system(minds: MindRegistry, ledger: SocialLedger, **extra: object) -> TournamentSystem:
    """A tournament system over the real strategies and payoffs."""
    return TournamentSystem(
        minds,
        build_strategy_registry(),
        load_payoffs(),
        ledger,
        **extra,  # type: ignore[arg-type]
    )


def run(world: World, tournament: TournamentSystem, ticks: int) -> None:
    for _ in range(ticks):
        tournament.step(world, world.clock.dt)
        world.clock = world.clock.advance()


# --------------------------------------------------------------- the arena


def test_the_ring_is_a_ring() -> None:
    positions = ring_positions(12, 200.0)

    radii = {round(math.hypot(x, z), 6) for x, z in positions}
    assert len(radii) == 1, "every contestant should be the same distance out"
    assert 0 < next(iter(radii)) < 100.0, "inside the world"
    assert len({(round(x, 3), round(z, 3)) for x, z in positions}) == 12, "no two in one spot"


def test_one_contestant_does_not_divide_by_zero() -> None:
    assert len(ring_positions(1, 100.0)) == 1
    assert ring_positions(0, 100.0) == []


def test_a_tournament_world_stands_its_agents_in_a_ring() -> None:
    world = IslandWorldBuilder().build(tournament_config(population=24))

    radii = {round(math.hypot(*agent.position)) for agent in world.living_agents()}
    assert len(radii) == 1, f"expected one ring, got radii {radii}"


def test_cohorts_are_equal_rather_than_drawn_from_the_mix() -> None:
    """A tournament asks how strategies compare; starting unequal asks less."""
    world = IslandWorldBuilder().build(tournament_config(population=27))

    counts = Counter(agent.strategy for agent in world.living_agents())
    assert max(counts.values()) - min(counts.values()) <= 1, counts


def test_an_island_world_is_not_a_ring() -> None:
    world = IslandWorldBuilder().build(
        WorldConfig(seed=5, population=24, max_agents=40, terrain=SMALL_TERRAIN)
    )

    radii = {round(math.hypot(*agent.position)) for agent in world.living_agents()}
    assert len(radii) > 1


# ------------------------------------------------------------- the schedule


def test_every_pair_meets_exactly_once(minds: MindRegistry, ledger: SocialLedger) -> None:
    world = IslandWorldBuilder().build(tournament_config(population=8))
    tournament = system(minds, ledger)

    tournament.step(world, world.clock.dt)

    # 8 agents -> 28 distinct pairs.
    assert len(tournament.state.pairs) == 28
    assert len(set(tournament.state.pairs)) == 28


def test_pairings_are_spread_over_ticks(minds: MindRegistry, ledger: SocialLedger) -> None:
    """A generation resolved in one frame would be unwatchable."""
    world = IslandWorldBuilder().build(tournament_config(population=12))
    tournament = system(minds, ledger, pairings_per_tick=5)

    tournament.step(world, world.clock.dt)

    assert tournament.state.pair_index == 5
    assert not tournament.state.complete


def test_rounds_are_iterated_not_one_shot(minds: MindRegistry, ledger: SocialLedger) -> None:
    """One round cannot tell Tit-for-Tat from a pushover.

    Only part of the schedule is played: finishing a generation resets the
    round counts for the next one, so asserting afterwards would read zeros.
    """
    world = IslandWorldBuilder().build(tournament_config(population=4))
    tournament = system(minds, ledger, rounds_per_pair=7, pairings_per_tick=2)

    tournament.step(world, world.clock.dt)

    assert not tournament.state.complete, "the generation must still be in progress"
    played = [count for count in tournament.state.rounds.values() if count > 0]
    assert played, "two pairings should have left a record"
    assert all(count % 7 == 0 for count in played)
    assert max(played) >= 7


# -------------------------------------------------------------- survival off


def test_nobody_starves_or_dies(minds: MindRegistry, ledger: SocialLedger) -> None:
    """Hunger would measure something other than the strategies."""
    world = IslandWorldBuilder().build(tournament_config(population=10))
    tournament = system(minds, ledger)
    before = len(world.living_agents())

    run(world, tournament, 400)

    assert len(world.living_agents()) == before
    assert world.deaths == 0
    assert min(agent.needs.hunger for agent in world.living_agents()) == 100.0


def test_no_food_changes_hands(minds: MindRegistry, ledger: SocialLedger) -> None:
    """The payoff is the score and nothing else."""
    world = IslandWorldBuilder().build(tournament_config(population=10))
    tournament = system(minds, ledger)
    before = sum(agent.inventory.food for agent in world.living_agents())

    run(world, tournament, 200)

    assert sum(agent.inventory.food for agent in world.living_agents()) == before


def test_the_system_does_nothing_on_an_island(minds: MindRegistry, ledger: SocialLedger) -> None:
    world = IslandWorldBuilder().build(
        WorldConfig(seed=5, population=10, max_agents=20, terrain=SMALL_TERRAIN)
    )
    tournament = system(minds, ledger)

    run(world, tournament, 50)

    assert tournament.state.scores == {}
    assert tournament.state.generation == 0


# ------------------------------------------------------------------ scoring


def test_scores_are_per_round_not_per_agent(minds: MindRegistry, ledger: SocialLedger) -> None:
    """Otherwise a strategy is rewarded for having more members this round."""
    world = IslandWorldBuilder().build(tournament_config(population=9))
    tournament = system(minds, ledger)
    run(world, tournament, 60)

    standings = tournament.state.average_by_strategy(world)

    assert standings, "someone should have played by now"
    matrix = load_payoffs().matrix(GameKind.PRISONERS_DILEMMA)
    # A per-round score has to sit inside the matrix; a per-agent total would
    # be ten times this and the assertion is what catches the difference.
    assert all(matrix.sucker <= score <= matrix.temptation for score in standings.values()), (
        standings
    )


def test_mutual_defectors_score_the_punishment(minds: MindRegistry, ledger: SocialLedger) -> None:
    """A sanity anchor on the arithmetic: all-defect pays P, not R."""
    world = IslandWorldBuilder().build(tournament_config(population=6))
    for agent in world.living_agents():
        agent.strategy = "AlwaysDefect"
    tournament = system(minds, ledger)

    run(world, tournament, 40)

    punishment = load_payoffs().matrix(GameKind.PRISONERS_DILEMMA).punishment
    standings = tournament.state.average_by_strategy(world)
    assert standings["AlwaysDefect"] == pytest.approx(punishment, abs=0.001)


def test_mutual_cooperators_score_the_reward(minds: MindRegistry, ledger: SocialLedger) -> None:
    world = IslandWorldBuilder().build(tournament_config(population=6))
    for agent in world.living_agents():
        agent.strategy = "AlwaysCooperate"
    tournament = system(minds, ledger)

    run(world, tournament, 40)

    reward = load_payoffs().matrix(GameKind.PRISONERS_DILEMMA).reward
    assert tournament.state.average_by_strategy(world)["AlwaysCooperate"] == pytest.approx(
        reward, abs=0.001
    )


# ------------------------------------------------------------- generations


def test_a_generation_resamples_the_population(minds: MindRegistry, ledger: SocialLedger) -> None:
    world = IslandWorldBuilder().build(tournament_config(population=12))
    tournament = system(minds, ledger)

    run(world, tournament, 600)

    assert tournament.state.generation >= 1
    assert len(world.living_agents()) == 12, "replicator dynamics keeps the population"


def test_the_tournament_stops_after_its_generations(
    minds: MindRegistry, ledger: SocialLedger
) -> None:
    world = IslandWorldBuilder().build(tournament_config(population=6))
    tournament = system(minds, ledger, generations=2)

    run(world, tournament, 3000)

    assert tournament.state.finished
    assert tournament.state.generation == 2

    # And then it really stops: no further scoring.
    scores = dict(tournament.state.scores)
    run(world, tournament, 50)
    assert tournament.state.scores == scores


def test_a_strategy_is_never_wiped_out_in_one_generation(
    minds: MindRegistry, ledger: SocialLedger
) -> None:
    """Permanent removal would stop the tournament being a comparison."""
    world = IslandWorldBuilder().build(tournament_config(population=18))
    tournament = system(minds, ledger)
    run(world, tournament, 400)
    standings = tournament.state.average_by_strategy(world)

    tournament.evolve(world, standings)

    counts = Counter(agent.strategy for agent in world.living_agents())
    assert len(counts) >= 2, "one generation should not collapse to a monoculture"


def test_changing_strategy_wipes_the_pair_history(
    minds: MindRegistry, ledger: SocialLedger
) -> None:
    """Or a fresh defector inherits a reputation for cooperating."""
    world = IslandWorldBuilder().build(tournament_config(population=8))
    tournament = system(minds, ledger)
    run(world, tournament, 300)
    agent = world.living_agents()[0]
    minds.require(agent.id).memory.relationship(999).trust = 0.9

    tournament.evolve(world, tournament.state.average_by_strategy(world))

    assert minds.require(agent.id).memory.social == {}


# ------------------------------------------------------- the actual finding


@pytest.mark.slow
def test_it_reproduces_axelrods_result(minds: MindRegistry, ledger: SocialLedger) -> None:
    """The point of the whole feature: nice reciprocators win.

    Axelrod's finding is that unconditional defection does well in the first
    round and then collapses once its victims are gone, while strategies that
    are nice, retaliatory and forgiving accumulate. If this test fails, either
    the payoffs or the strategies are wrong - it is the one test that checks
    the simulation says something true about the world.
    """
    config = load_preset("axelrod_tournament", Path("config"))
    assert config is not None
    world = IslandWorldBuilder().build(
        config.apply_to(WorldConfig(seed=1337, terrain=ARENA_TERRAIN, max_agents=120))
    )
    tournament = system(minds, ledger, generations=12)

    for _ in range(30_000):
        tournament.step(world, world.clock.dt)
        world.clock = world.clock.advance()
        if tournament.state.finished:
            break

    assert tournament.state.finished, "12 generations should finish inside 30k ticks"

    final = Counter(agent.strategy for agent in world.living_agents())
    standings = tournament.state.average_by_strategy(world)
    nice = {"TitForTat", "GenerousTFT", "Pavlov", "Grudger", "AlwaysCooperate"}

    share_of_nice = sum(count for name, count in final.items() if name in nice) / sum(
        final.values()
    )
    assert share_of_nice > 0.6, f"reciprocators should dominate, got {final}"
    assert final.get("AlwaysDefect", 0) < sum(final.values()) * 0.15, (
        f"unconditional defection should have collapsed, got {final}"
    )
    # And the population should be earning close to the cooperative payoff.
    assert max(standings.values()) > 2.7, standings
