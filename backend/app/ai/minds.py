"""Per-agent mind state, kept out of `sim/`.

`sim.entities.Agent` holds only what the world needs to simulate and draw an
agent. Memory, the decision trace and the running skill live here, because
`ai/` may read `sim/` but never the other way round (ADR 0001).
"""

from dataclasses import dataclass, field

from app.ai.brains.base import ScoredOption
from app.ai.memory import AgentMemory
from app.ai.perception import Observation
from app.ai.skills.base import SkillRun
from app.sim.world import World


@dataclass(slots=True)
class Mind:
    """Everything an agent knows and is currently doing.

    Attributes:
        memory: Episodic and social memory.
        observation: What it last perceived.
        trace: Top scored options from the last decision, for the inspector.
        reason: Why the chosen skill won.
        run: The skill currently executing, if any.
        cooldowns: `skill name -> sim-seconds` before it may run again.
        last_decision_s: Sim-time of the last decision, for review throttling.
    """

    memory: AgentMemory = field(default_factory=AgentMemory)
    observation: Observation | None = None
    trace: tuple[ScoredOption, ...] = ()
    reason: str = ""
    run: SkillRun | None = None
    cooldowns: dict[str, float] = field(default_factory=dict)
    last_decision_s: float = -1.0

    false_lead: tuple[float, float] | None = None
    """Somewhere an agent has been told there is food, where there is none.

    This is what makes lying cost the victim something real: they walk there,
    find nothing, and have wasted the time. If they work out who sent them,
    the liar pays for it.
    """
    false_lead_from: int | None = None
    false_lead_until: float = 0.0

    def plant_false_lead(self, liar_id: int, where: tuple[float, float], until: float) -> None:
        """Record a lie about where food is."""
        self.false_lead = where
        self.false_lead_from = liar_id
        self.false_lead_until = until

    def take_false_lead(self, now_s: float) -> tuple[float, float] | None:
        """Return an unexpired false lead, if this agent is still fooled."""
        if self.false_lead is None or now_s > self.false_lead_until:
            return None
        return self.false_lead

    def clear_false_lead(self) -> int | None:
        """Forget the lead and return who planted it."""
        liar = self.false_lead_from
        self.false_lead = None
        self.false_lead_from = None
        self.false_lead_until = 0.0
        return liar

    def is_ready(self, skill: str, now_s: float) -> bool:
        """Whether `skill` is off cooldown at `now_s`."""
        return self.cooldowns.get(skill, 0.0) <= now_s

    def start_cooldown(self, skill: str, now_s: float, cooldown: float) -> None:
        """Record that `skill` may not run again until `cooldown` has passed."""
        if cooldown > 0.0:
            self.cooldowns[skill] = now_s + cooldown


class MindRegistry:
    """Minds by agent id, reset whenever the world is rebuilt.

    Keyed on the world's `uid` rather than object identity, so a reset can
    never leak one world's memories into the next.
    """

    __slots__ = ("_minds", "_world_uid")

    def __init__(self) -> None:
        self._minds: dict[int, Mind] = {}
        self._world_uid: int | None = None

    def __len__(self) -> int:
        return len(self._minds)

    def __contains__(self, agent_id: object) -> bool:
        return agent_id in self._minds

    def on_world_replaced(self, world: World) -> None:
        """Forget everything; `world` is a different world now."""
        self._minds.clear()
        self._world_uid = world.uid

    def sync(self, world: World) -> None:
        """Create minds for new agents and drop minds for departed ones."""
        if world.uid != self._world_uid:
            self.on_world_replaced(world)

        living = {agent.id for agent in world.living_agents()}
        for agent_id in living - self._minds.keys():
            self._minds[agent_id] = Mind()
        for agent_id in self._minds.keys() - living:
            del self._minds[agent_id]

    def get(self, agent_id: int) -> Mind | None:
        """Return the mind for `agent_id`, or `None`."""
        return self._minds.get(agent_id)

    def require(self, agent_id: int) -> Mind:
        """Return the mind for `agent_id`, creating it if needed."""
        mind = self._minds.get(agent_id)
        if mind is None:
            mind = Mind()
            self._minds[agent_id] = mind
        return mind

    def items(self) -> list[tuple[int, Mind]]:
        """Return `(agent_id, mind)` pairs in stable id order."""
        return sorted(self._minds.items())
