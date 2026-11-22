"""Spawning the starting population from `WorldConfig` (SPEC section 4)."""

import math
from collections.abc import Mapping

import numpy as np

from app.core.world_config import StrategyName, WorldConfig
from app.sim import balance
from app.sim.entities import Agent, Biome, BrainType, LifeStage, Traits
from app.sim.names import make_name
from app.sim.world import World
from app.sim.worldgen.grid import cells_in_biomes, jittered_positions

SPAWN_BIOMES: tuple[Biome, ...] = (Biome.MEADOW, Biome.BEACH, Biome.FOREST)

TRAIT_NAMES: tuple[str, ...] = (
    "aggression",
    "honesty",
    "loyalty",
    "greed",
    "sociability",
    "cunning",
    "courage",
    "charisma",
)


def life_stage_for(age: float) -> LifeStage:
    """Return the life stage for `age` in years."""
    if age < balance.CHILD_UNTIL:
        return LifeStage.CHILD
    if age >= balance.ELDER_FROM:
        return LifeStage.ELDER
    return LifeStage.ADULT


TRAIT_CONCENTRATION = 4.8
"""Total beta concentration. Higher means personalities cluster harder."""

TRAIT_BIAS_LIMITS = (0.05, 0.95)
"""A bias is clamped to this: a world of pure saints has nothing to show."""


def random_traits(rng: np.random.Generator, bias: Mapping[str, float] | None = None) -> Traits:
    """Draw a personality, optionally centred away from the middle.

    Beta shaping keeps most agents near their mean. `bias` moves that mean per
    trait (`{"honesty": 0.2}` makes a dishonest world) by solving the beta
    parameters for it, which preserves the spread - so a dishonest world still
    produces the occasional honest agent, rather than clamping everyone.
    """
    means = np.full(len(TRAIT_NAMES), 0.5)
    if bias:
        low, high = TRAIT_BIAS_LIMITS
        for index, name in enumerate(TRAIT_NAMES):
            if name in bias:
                means[index] = min(high, max(low, float(bias[name])))
    # One vectorised draw, so the RNG stream is consumed identically whether
    # or not a bias is set.
    values = rng.beta(TRAIT_CONCENTRATION * means, TRAIT_CONCENTRATION * (1.0 - means))
    return Traits(**{name: float(values[index]) for index, name in enumerate(TRAIT_NAMES)})


def _strategy_pool(config: WorldConfig, rng: np.random.Generator, count: int) -> list[StrategyName]:
    """Draw `count` strategies from the configured mix, in a stable order."""
    mix = config.normalised_strategy_mix
    names: list[StrategyName] = sorted(mix)
    weights = np.array([mix[name] for name in names], dtype=np.float64)
    weights /= weights.sum()
    draws = rng.choice(len(names), size=count, p=weights)
    return [names[int(index)] for index in draws]


def spawn_population(world: World, config: WorldConfig) -> None:
    """Fill `world.agents` deterministically from the spawn RNG stream."""
    rng = world.rngs["spawn"]
    count = min(config.population, config.max_agents)
    if count <= 0:
        return

    candidates = cells_in_biomes(world.terrain, SPAWN_BIOMES)
    if candidates.size == 0:
        candidates = cells_in_biomes(world.terrain, (Biome.HILLS,))
    cells = rng.choice(candidates, size=count, replace=candidates.size < count)
    positions = jittered_positions(world.terrain, np.sort(cells), rng)

    strategies = _strategy_pool(config, rng, count)
    ages = rng.uniform(balance.CHILD_UNTIL + 2.0, balance.ELDER_FROM - 5.0, size=count)
    headings = rng.uniform(0.0, math.tau, size=count)
    used_names: set[str] = set()

    for index in range(count):
        age = float(ages[index])
        agent = Agent(
            id=world.next_agent_id,
            name=make_name(rng, used_names),
            position=positions[index],
            traits=random_traits(rng, config.trait_bias),
            strategy=strategies[index],
            brain_type=BrainType.LLM if index < config.llm_agents else BrainType.UTILITY,
            age=age,
            life_stage=life_stage_for(age),
            heading=float(headings[index]),
        )
        world.agents[agent.id] = agent
        world.next_agent_id += 1

    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )
