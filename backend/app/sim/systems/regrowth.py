"""Resource regrowth, winter scarcity and corpses rotting away (SPEC 3.1)."""

from app.sim import balance
from app.sim.entities import ResourceKind
from app.sim.world import World


class RegrowthSystem:
    """Refills harvested nodes, and removes corpses once they are gone.

    Winter stops berry regrowth entirely, which is what makes "Harsh Winter"
    a different game rather than just a slower one.
    """

    name = "regrowth"

    __slots__ = ()

    def step(self, world: World, dt: float) -> None:
        """Regrow every node by `dt`, scaled by the scarcity divisor."""
        winter = world.clock.season == "winter"
        divisor = max(0.1, world.scarcity)
        expired: list[int] = []

        for node_id in sorted(world.resources):
            node = world.resources[node_id]

            if node.kind is ResourceKind.CORPSE:
                node.amount -= node.capacity / balance.CORPSE_DECAY_S * dt
                if node.amount <= 0.0:
                    expired.append(node_id)
                continue

            if node.infinite or node.amount >= node.capacity:
                continue

            rate = node.regrowth_per_sim_s
            if winter and node.kind is ResourceKind.BERRY_BUSH:
                rate *= balance.WINTER_REGROWTH_FACTOR
            if rate <= 0.0:
                continue
            node.amount = min(node.capacity, node.amount + rate * dt / divisor)

        for node_id in expired:
            world.resources.pop(node_id, None)
            world.resource_index.remove(node_id)
