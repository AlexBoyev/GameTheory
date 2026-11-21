"""Hunting: the solo rabbit chase (SPEC section 7.3).

Deer need two hunters and therefore a Stag Hunt, which arrives with the game
theory in Phase 4; `JoinHunt` lands with it.
"""

from pydantic import BaseModel, ConfigDict

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import nearest_resource, need_urgency, steer_towards, stop
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, ResourceKind
from app.sim.events import EventType, SimEvent
from app.sim.world import World

RABBITS: frozenset[ResourceKind] = frozenset({ResourceKind.RABBIT})
MAX_ATTEMPTS = 3
MIN_ENERGY_TO_HUNT = 20.0


class HuntParams(BaseModel):
    """Which rabbit to chase; defaults to the nearest one."""

    model_config = ConfigDict(extra="forbid")

    resource_id: int | None = None


def _resolve_rabbit(agent: Agent, world: World, params: BaseModel) -> int | None:
    """Return the requested rabbit's id, or the nearest rabbit's id."""
    if isinstance(params, HuntParams) and params.resource_id is not None:
        node = world.resources.get(params.resource_id)
        return node.id if node is not None and not node.depleted else None
    node = nearest_resource(world, agent, RABBITS)
    return node.id if node is not None else None


class HuntRabbit(Skill):
    """Chase a rabbit; catching it is a dice roll weighted by courage."""

    name = "HuntRabbit"
    description = "Chase and catch a rabbit for a small amount of food."
    category = SkillCategory.SURVIVAL
    Params = HuntParams
    visual_state = AgentState.HUNT
    cooldown = 4.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require energy for the chase and a rabbit to chase."""
        if agent.needs.energy < MIN_ENERGY_TO_HUNT:
            return Err("too tired to hunt")
        if _resolve_rabbit(agent, world, params) is None:
            return Err("no rabbit in sight")
        return OK_NONE

    def utility(self, agent: Agent, ctx: DecisionContext) -> float:
        """Brave, hungry agents hunt; timid or well-fed ones gather instead."""
        hunger = need_urgency(agent.needs.hunger)
        stock = min(1.0, agent.inventory.food / balance.CARRY_TARGET)
        return hunger * (0.35 + 0.65 * agent.traits.courage) * (1.0 - 0.6 * stock)

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Lock on to a rabbit."""
        rabbit_id = _resolve_rabbit(agent, world, params)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={
                "node": -1 if rabbit_id is None else rabbit_id,
                "arrived": False,
                "attempts": 0,
                "since_attempt": 0.0,
            },
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Close the distance, then roll for the catch once a second."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        rabbit = world.resources.get(int(run.state["node"]))

        if rabbit is None or rabbit.depleted:
            stop(agent)
            return SkillStatus.FAILED

        if not run.state["arrived"]:
            if not steer_towards(agent, rabbit.position):
                return SkillStatus.RUNNING
            run.state["arrived"] = True

        run.state["since_attempt"] = float(run.state["since_attempt"]) + dt
        if float(run.state["since_attempt"]) < balance.HUNT_ATTEMPT_INTERVAL:
            return SkillStatus.RUNNING

        run.state["since_attempt"] = 0.0
        run.state["attempts"] = int(run.state["attempts"]) + 1

        if float(world.rngs["action"].random()) < self._catch_chance(agent):
            return self._catch(world, agent, rabbit_id=rabbit.id)

        if int(run.state["attempts"]) >= MAX_ATTEMPTS:
            stop(agent)
            return SkillStatus.FAILED
        return SkillStatus.RUNNING

    @staticmethod
    def _catch_chance(agent: Agent) -> float:
        """Return the per-attempt catch probability for `agent`."""
        stamina = max(0.3, min(1.0, agent.needs.energy / balance.NEED_MAX))
        return balance.HUNT_CATCH_BASE * (0.5 + 0.5 * agent.traits.courage) * stamina

    @staticmethod
    def _catch(world: World, agent: Agent, rabbit_id: int) -> SkillStatus:
        """Consume the rabbit, feed the hunter and announce it."""
        rabbit = world.resources[rabbit_id]
        rabbit.amount = 0.0
        agent.inventory.food += balance.RABBIT_FOOD
        stop(agent)
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.HUNT,
                summary=f"{agent.name} caught a rabbit",
                actors=(agent.id,),
                importance=3,
                position=agent.position,
                data={"food": balance.RABBIT_FOOD},
            )
        )
        return SkillStatus.DONE
