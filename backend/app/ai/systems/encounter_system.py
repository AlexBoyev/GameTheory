"""Deciding who meets whom, and letting the resolver do the rest.

Two guards keep this from dominating a tick: a per-pair cooldown, so the same
two agents do not replay the same dilemma ten times a second, and a budget on
encounters per tick, so a crowd at a waterhole cannot stall the simulation.
"""

from app.ai.gametheory.ledger import SocialLedger
from app.ai.gametheory.resolver import EncounterResolver
from app.ai.minds import MindRegistry
from app.sim import balance
from app.sim.entities import Agent, AgentState
from app.sim.world import INTERACTION_RADIUS, World

ENCOUNTER_COOLDOWN_SIM_S = 12.0
"""How long a pair must wait before playing again."""

MAX_ENCOUNTERS_PER_TICK = 24
CHECK_INTERVAL_TICKS = 3
"""Pairs are looked for twice a sim-second, not ten times."""

SOCIAL_RESTORE_PER_SIM_S = 6.0
"""Company is its own reward: standing near someone restores the social need.

Without this the social drive only ever falls, which made the inspector show
a permanently empty bar and gave sociability nothing to attach to.
"""

BUSY_STATES = frozenset({AgentState.SLEEP, AgentState.FLEE, AgentState.DEAD})


class EncounterSystem:
    """Pairs up nearby agents and resolves a game between them."""

    name = "encounters"

    __slots__ = ("_cooldowns", "_ledger", "_minds", "_resolver")

    def __init__(
        self,
        minds: MindRegistry,
        resolver: EncounterResolver,
        ledger: SocialLedger,
    ) -> None:
        self._minds = minds
        self._resolver = resolver
        self._ledger = ledger
        self._cooldowns: dict[tuple[int, int], float] = {}

    def on_world_replaced(self, world: World) -> None:
        """Forget every pairing; this is a different world."""
        self._cooldowns.clear()
        self._ledger.clear()

    def step(self, world: World, dt: float) -> None:
        """Find adjacent pairs, socialise them, and maybe play a game."""
        now = world.clock.sim_seconds
        social_gain = SOCIAL_RESTORE_PER_SIM_S * dt
        agents = world.living_agents()

        seen: set[tuple[int, int]] = set()
        budget = MAX_ENCOUNTERS_PER_TICK
        check_pairs = world.clock.tick % CHECK_INTERVAL_TICKS == 0

        for agent in agents:
            # Through the world's memo, like every other spatial question:
            # the decision phase has already asked this for the agents that
            # deliberated this tick, and a second path to the index is how
            # a cache quietly stops covering half the calls.
            neighbours = world.neighbours_within(agent.id, INTERACTION_RADIUS)
            if not neighbours:
                continue

            # Company satisfies the social need whatever else happens.
            agent.needs.social = min(balance.NEED_MAX, agent.needs.social + social_gain)
            if not check_pairs or budget <= 0:
                continue

            for other_id in sorted(neighbours):
                other = world.agents.get(other_id)
                if other is None or not other.alive:
                    continue

                pair = (agent.id, other_id) if agent.id < other_id else (other_id, agent.id)
                if pair in seen:
                    continue
                seen.add(pair)

                if not self._available(agent) or not self._available(other):
                    continue
                if now - self._cooldowns.get(pair, -ENCOUNTER_COOLDOWN_SIM_S) < (
                    ENCOUNTER_COOLDOWN_SIM_S
                ):
                    continue

                first, second = (agent, other) if agent.id < other_id else (other, agent)
                result = self._resolver.resolve(world, first, second)
                self._cooldowns[pair] = now
                if result is None:
                    continue

                self._ledger.record_encounter(result, first.strategy, second.strategy)
                budget -= 1
                if budget <= 0:
                    break

        self._forget_old(now)

    @staticmethod
    def _available(agent: Agent) -> bool:
        """Whether an agent is in a state to be drawn into an encounter."""
        return agent.alive and agent.state not in BUSY_STATES

    def _forget_old(self, now: float) -> None:
        """Drop cooldowns that have expired, so the map cannot grow forever."""
        if len(self._cooldowns) < 4096:
            return
        cutoff = now - ENCOUNTER_COOLDOWN_SIM_S
        self._cooldowns = {pair: at for pair, at in self._cooldowns.items() if at >= cutoff}
