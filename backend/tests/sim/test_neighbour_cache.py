"""The per-tick neighbour memo: it must be a memo, never a stale answer."""

import pytest

from app.ai.skills.helpers import nearest_resource
from app.ai.skills.targeting import nearby_agents
from app.core.world_config import WorldConfig
from app.sim.spatial_hash import SpatialHash
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder
from tests.conftest import SMALL_TERRAIN


def build() -> World:
    config = WorldConfig(seed=5, population=8, max_agents=32, terrain=SMALL_TERRAIN)
    return IslandWorldBuilder().build(config)


def test_the_same_question_is_answered_once_per_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured at 300 agents: 132 calls a tick, 20 distinct questions."""
    world = build()
    first, second = world.living_agents()[:2]
    second.position = first.position
    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )

    queries = 0
    original = SpatialHash.neighbours

    def counting(self: SpatialHash, item_id: int, radius: float) -> list[int]:
        nonlocal queries
        queries += 1
        return original(self, item_id, radius)

    monkeypatch.setattr(SpatialHash, "neighbours", counting)

    for _ in range(6):
        assert second.id in world.neighbours_within(first.id, 4.0)

    assert queries == 1, "six asks of one question should cost one spatial query"


def test_a_new_tick_asks_again() -> None:
    world = build()
    first = world.living_agents()[0]
    world.neighbours_within(first.id, 4.0)

    world.clock = world.clock.advance()
    far_away = world.living_agents()[1]
    far_away.position = first.position
    world.agent_index.insert(far_away.id, *far_away.position)

    assert far_away.id in world.neighbours_within(first.id, 4.0)


def test_movement_drops_the_cache() -> None:
    """A cached list must not outlive the positions it was computed from.

    Positions change in `MovementSystem`, which rebuilds the index.
    """
    world = build()
    first, second = world.living_agents()[:2]
    second.position = (first.position[0] + 100.0, first.position[1])
    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )
    assert second.id not in world.neighbours_within(first.id, 4.0)

    second.position = first.position
    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )

    # Nobody told the cache; the index version did.
    assert second.id in world.neighbours_within(first.id, 4.0)


def test_a_death_drops_the_cache() -> None:
    world = build()
    first, second = world.living_agents()[:2]
    second.position = first.position
    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )
    assert nearby_agents(world, first, 4.0)

    second.alive = False
    world.agent_index.remove(second.id)
    world.invalidate_living()

    assert not nearby_agents(world, first, 4.0), "the dead are not neighbours"


def test_a_resource_scan_survives_a_node_emptying_but_not_a_node_appearing() -> None:
    """The scan is memoised; the answer is not.

    A node emptied mid-tick must still be rejected (ADR 0005), and a node
    that appears mid-tick - a corpse - must be found.
    """
    from app.sim.entities import ResourceKind
    from tests.factories import place

    world = build()
    agent = world.living_agents()[0]
    agent.position = (0.0, 0.0)
    world.agent_index.insert(agent.id, 0.0, 0.0)
    world.resources.clear()
    world.resource_index.clear()
    bush = place(world, ResourceKind.BERRY_BUSH, (1.0, 0.0))

    assert nearest_resource(world, agent, frozenset({ResourceKind.BERRY_BUSH})) is bush

    bush.amount = 0.0
    assert nearest_resource(world, agent, frozenset({ResourceKind.BERRY_BUSH})) is None

    later = place(world, ResourceKind.BERRY_BUSH, (2.0, 0.0))
    assert nearest_resource(world, agent, frozenset({ResourceKind.BERRY_BUSH})) is later
