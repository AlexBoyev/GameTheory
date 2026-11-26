"""Radius-limited perception: what an agent can actually see (SPEC 7.1).

Agents act on an `Observation`, not on the world, which is what keeps
information asymmetry - and therefore lying - meaningful later on.
"""

from dataclasses import dataclass, field

from app.sim import balance
from app.sim.entities import ResourceKind
from app.sim.world import World

DEFAULT_VISION_RADIUS: float = balance.VISION_RADIUS

_VISIBLE_FOOD: frozenset[ResourceKind] = frozenset({ResourceKind.BERRY_BUSH, ResourceKind.CORPSE})
"""Food an agent can spot from a distance - animals have to be hunted."""


@dataclass(frozen=True, slots=True)
class Observation:
    """One agent's view of its surroundings at a tick.

    Attributes:
        tick: When it was taken.
        agent_id: The observer.
        visible_agents: Living agent ids within vision radius.
        visible_resources: Non-depleted resource ids grouped by kind.
        nearest_water: Position of the closest drinkable water, if any.
        nearest_food: Position of the closest edible resource, if any.
        threat_id: The nearest agent aggressive enough to worry about.
        on_biome: Biome ordinal under the observer.
        is_night: Whether it is night (drives sleep urges).
    """

    tick: int
    agent_id: int
    visible_agents: tuple[int, ...] = ()
    visible_resources: dict[ResourceKind, tuple[int, ...]] = field(default_factory=dict)
    nearest_water: tuple[float, float] | None = None
    nearest_food: tuple[float, float] | None = None
    threat_id: int | None = None
    on_biome: int = 0
    is_night: bool = False

    def resources_of(self, kind: ResourceKind) -> tuple[int, ...]:
        """Return visible resource ids of `kind`."""
        return self.visible_resources.get(kind, ())

    @property
    def has_company(self) -> bool:
        """Whether anyone else is in sight."""
        return bool(self.visible_agents)


class Perception:
    """Builds `Observation`s from the spatial indices."""

    __slots__ = ("vision_radius",)

    def __init__(self, vision_radius: float = DEFAULT_VISION_RADIUS) -> None:
        self.vision_radius = vision_radius

    def observe(self, world: World, agent_id: int) -> Observation:
        """Return what `agent_id` can perceive right now."""
        agent = world.agents[agent_id]
        x, z = agent.position

        visible_agents = tuple(
            other_id
            for other_id in world.neighbours_within(agent_id, self.vision_radius)
            if (other := world.agents.get(other_id)) is not None and other.alive
        )

        grouped: dict[ResourceKind, list[int]] = {}
        nearest_water: tuple[float, float] | None = None
        nearest_food: tuple[float, float] | None = None
        water_distance = float("inf")
        food_distance = float("inf")

        for node_id in world.resources_within(agent_id, (x, z), self.vision_radius):
            node = world.resources.get(node_id)
            if node is None or node.depleted:
                continue
            grouped.setdefault(node.kind, []).append(node_id)
            distance = (node.position[0] - x) ** 2 + (node.position[1] - z) ** 2
            if node.kind is ResourceKind.WATER and distance < water_distance:
                water_distance, nearest_water = distance, node.position
            elif node.kind in _VISIBLE_FOOD and distance < food_distance:
                food_distance, nearest_food = distance, node.position

        return Observation(
            tick=world.clock.tick,
            agent_id=agent_id,
            visible_agents=visible_agents,
            visible_resources={kind: tuple(ids) for kind, ids in grouped.items()},
            nearest_water=nearest_water,
            nearest_food=nearest_food,
            threat_id=self._nearest_threat(world, agent_id, visible_agents),
            on_biome=world.terrain.biome_at(x, z),
            is_night=world.clock.is_night,
        )

    @staticmethod
    def _nearest_threat(
        world: World,
        agent_id: int,
        visible_agents: tuple[int, ...],
    ) -> int | None:
        """Return the closest aggressive neighbour inside the threat radius."""
        agent = world.agents[agent_id]
        x, z = agent.position
        threat_radius_squared = balance.THREAT_RADIUS**2
        closest: int | None = None
        closest_distance = float("inf")

        for other_id in visible_agents:
            other = world.agents[other_id]
            if other.traits.aggression < balance.THREAT_AGGRESSION:
                continue
            distance = (other.position[0] - x) ** 2 + (other.position[1] - z) ** 2
            if distance <= threat_radius_squared and distance < closest_distance:
                closest_distance, closest = distance, other_id
        return closest
