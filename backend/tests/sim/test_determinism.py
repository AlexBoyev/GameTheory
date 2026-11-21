"""The contract that makes this a laboratory: same seed, same world.

CLAUDE.md architecture rule 7. If this test ever goes red, a result from any
earlier run stops meaning anything, so it is deliberately strict: a thousand
ticks of the full pipeline, compared to the last bit.
"""

from app.ai.minds import MindRegistry
from app.ai.skills.registry import build_registry
from app.core.world_config import WorldConfig
from app.services.engine_factory import build_pipeline
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder
from tests.conftest import SMALL_TERRAIN, run_ticks

TICKS = 1000


def fingerprint(world: World) -> tuple[object, ...]:
    """Return a complete, hashable summary of the simulation state."""
    agents = tuple(
        (
            agent.id,
            agent.name,
            agent.position,
            agent.velocity,
            agent.heading,
            agent.health,
            agent.age,
            agent.alive,
            agent.state.value,
            agent.current_skill,
            agent.needs.hunger,
            agent.needs.thirst,
            agent.needs.energy,
            agent.needs.safety,
            agent.needs.social,
            agent.inventory.food,
        )
        for _, agent in sorted(world.agents.items())
    )
    resources = tuple(
        (node.id, node.kind.value, node.position, node.amount)
        for _, node in sorted(world.resources.items())
    )
    return (world.clock.tick, world.population, world.deaths, agents, resources)


def simulate(seed: int, ticks: int = TICKS, population: int = 30) -> World:
    """Build a world and run it, with a fresh pipeline and fresh minds."""
    config = WorldConfig(
        seed=seed,
        population=population,
        max_agents=64,
        terrain=SMALL_TERRAIN,
    )
    world = IslandWorldBuilder().build(config)
    pipeline = build_pipeline(MindRegistry(), build_registry(), temperature=0.35)
    pipeline.on_world_replaced(world)
    run_ticks(pipeline, world, ticks)
    return world


def test_same_seed_gives_an_identical_world_after_1000_ticks() -> None:
    first = simulate(seed=1234)
    second = simulate(seed=1234)

    assert first.clock.tick == TICKS
    assert fingerprint(first) == fingerprint(second)


def test_different_seeds_diverge() -> None:
    assert fingerprint(simulate(seed=1)) != fingerprint(simulate(seed=2))


def test_terrain_is_identical_for_a_seed_and_differs_across_seeds() -> None:
    builder = IslandWorldBuilder()
    config = WorldConfig(seed=99, population=1, terrain=SMALL_TERRAIN)

    first = builder.build(config)
    second = builder.build(config)
    other = builder.build(config.model_copy(update={"seed": 100}))

    assert (first.terrain.heights == second.terrain.heights).all()
    assert (first.terrain.biomes == second.terrain.biomes).all()
    assert (first.terrain.heights != other.terrain.heights).any()


def test_rebuilding_restarts_agent_ids_and_the_clock() -> None:
    builder = IslandWorldBuilder()
    config = WorldConfig(seed=5, population=10, terrain=SMALL_TERRAIN)

    first = builder.build(config)
    second = builder.build(config)

    assert first.uid != second.uid, "each build must be distinguishable"
    assert sorted(first.agents) == sorted(second.agents)
    assert second.clock.tick == 0
