"""The world must be survivable.

A simulation that quietly kills everyone is not a harsh world, it is a broken
one - and the failure is invisible from a unit test of any single system. This
is the guard: run a real population for a real stretch of time and insist that
most of them live, with a named cause when they do not.

The two bugs this test was written for, both of which passed every other test:

* fear drained 23x faster than it recovered, so a crowded island panicked
  itself to death instead of drinking;
* drinking spots were placed offshore, where movement cannot reach them, so
  agents died of thirst beside a visible lake.
"""

from collections import Counter

from app.ai.minds import MindRegistry
from app.ai.skills.registry import build_registry
from app.core.world_config import WorldConfig
from app.services.engine_factory import build_pipeline
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder
from tests.conftest import run_ticks

POPULATION = 60
TICKS = 6000
"""Long enough for thirst (200 sim-s) and hunger (285 sim-s) to bite twice."""

MIN_SURVIVAL_RATE = 0.8


def simulate() -> World:
    """Run a default-balance world for `TICKS` ticks."""
    config = WorldConfig(seed=2024, population=POPULATION, max_agents=POPULATION)
    world = IslandWorldBuilder().build(config)
    pipeline = build_pipeline(MindRegistry(), build_registry(), temperature=0.35)
    pipeline.on_world_replaced(world)
    run_ticks(pipeline, world, TICKS)
    return world


def test_most_of_the_population_survives_a_long_run() -> None:
    world = simulate()
    causes = Counter(
        agent.death_cause.value
        for agent in world.agents.values()
        if not agent.alive and agent.death_cause is not None
    )

    survival_rate = world.population / POPULATION
    assert survival_rate >= MIN_SURVIVAL_RATE, (
        f"only {world.population}/{POPULATION} survived {TICKS} ticks; deaths: {dict(causes)}"
    )


def test_survivors_are_not_merely_clinging_on() -> None:
    world = simulate()
    survivors = world.living_agents()

    average_thirst = sum(agent.needs.thirst for agent in survivors) / len(survivors)
    average_hunger = sum(agent.needs.hunger for agent in survivors) / len(survivors)

    assert average_thirst > 50.0, f"the island cannot keep agents watered ({average_thirst:.0f})"
    assert average_hunger > 50.0, f"the island cannot keep agents fed ({average_hunger:.0f})"


def test_agents_actually_use_the_world() -> None:
    """A world where nobody eats or drinks is suspiciously peaceful."""
    world = simulate()
    harvested = [
        node
        for node in world.resources.values()
        if not node.infinite and node.amount < node.capacity
    ]

    assert harvested, "nothing was ever harvested - are the skills running?"
    assert any(agent.inventory.food > 0.0 for agent in world.living_agents())
