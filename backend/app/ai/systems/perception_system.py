"""Refreshing observations, and letting fear push safety down."""

from app.ai.minds import MindRegistry
from app.ai.perception import Perception
from app.sim.world import World

PERCEPTION_INTERVAL_TICKS = 5
"""Observe every agent twice a sim-second, staggered across ticks.

Perceiving all 500 agents every tick would make spatial queries the dominant
cost of the simulation for no behavioural gain - half a second of staleness is
invisible in a world where walking somewhere takes several seconds.
"""

THREAT_FEAR_RATE = 7.0
"""Safety lost per sim-second while a threatening agent is close.

Paired with `balance.SAFETY_RECOVERY`: a scare should cost a few seconds of
composure, not pin an agent in panic for the rest of its life.
"""


class PerceptionSystem:
    """Keeps each mind's `Observation` fresh and applies fear."""

    name = "perception"

    __slots__ = ("_minds", "_perception")

    def __init__(self, minds: MindRegistry, perception: Perception | None = None) -> None:
        self._minds = minds
        self._perception = perception or Perception()

    def on_world_replaced(self, world: World) -> None:
        """Drop every mind: this is a different world."""
        self._minds.on_world_replaced(world)

    def step(self, world: World, dt: float) -> None:
        """Refresh the observations due this tick."""
        self._minds.sync(world)
        tick = world.clock.tick

        for agent in world.living_agents():
            mind = self._minds.require(agent.id)
            due = mind.observation is None or (agent.id + tick) % PERCEPTION_INTERVAL_TICKS == 0
            if due:
                mind.observation = self._perception.observe(world, agent.id)

            observation = mind.observation
            if observation is not None and observation.threat_id is not None:
                agent.needs.safety = max(0.0, agent.needs.safety - THREAT_FEAR_RATE * dt)
