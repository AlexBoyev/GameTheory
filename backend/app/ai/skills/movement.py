"""Moving around: Wander, MoveTo, Flee (SPEC section 7.3)."""

import math

from pydantic import BaseModel, ConfigDict

from app.ai.brains.base import DecisionContext
from app.ai.skills.base import Consideration, NoParams, Skill, SkillCategory, SkillRun, SkillStatus
from app.ai.skills.helpers import (
    distance_to,
    nearest_threat,
    need_urgency,
    steer_away,
    steer_towards,
    stop,
)
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState
from app.sim.world import World

MOVE_TO_TIMEOUT_S = 20.0
WANDER_UTILITY = 0.08
"""Deliberately tiny: wandering is what an agent does when nothing else wins."""


class MoveToParams(BaseModel):
    """A world position to walk to."""

    model_config = ConfigDict(extra="forbid")

    x: float
    z: float


class FleeParams(BaseModel):
    """Who to run from; defaults to the nearest threat."""

    model_config = ConfigDict(extra="forbid")

    from_agent: int | None = None


class Wander(Skill):
    """Stroll in a random direction for a few seconds."""

    name = "Wander"
    description = "Walk in no particular direction for a few seconds."
    category = SkillCategory.SURVIVAL
    Params = NoParams
    visual_state = AgentState.WANDER

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Always available - this is the fallback behaviour."""
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """A small constant, so any real need outranks doing nothing."""
        return [Consideration("nothing better to do", 1.0, WANDER_UTILITY)]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Pick a direction and a duration from the action RNG stream."""
        rng = world.rngs["action"]
        heading = float(rng.uniform(0.0, math.tau))
        duration = float(rng.uniform(balance.WANDER_MIN_DURATION, balance.WANDER_MAX_DURATION))
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"heading": heading, "duration": duration},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Keep walking; pick a new heading if the shoreline blocks the way."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        if run.elapsed >= float(run.state["duration"]):
            stop(agent)
            return SkillStatus.DONE

        heading = float(run.state["heading"])
        if agent.velocity == (0.0, 0.0) and run.elapsed > dt:
            # Movement refused the step: we walked into water, so turn.
            heading = (heading + math.pi * 0.6) % math.tau
            run.state["heading"] = heading

        speed = balance.WALK_SPEED * 0.55
        agent.velocity = (math.sin(heading) * speed, math.cos(heading) * speed)
        return SkillStatus.RUNNING


class MoveTo(Skill):
    """Walk to a specific position. Only an explicit plan can call this."""

    name = "MoveTo"
    description = "Walk to a specific world position."
    category = SkillCategory.SURVIVAL
    Params = MoveToParams
    visual_state = AgentState.MOVE
    autonomous = False

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Reject targets that are off the island or in the water."""
        target = params if isinstance(params, MoveToParams) else None
        if target is None:
            return Err("MoveTo needs x and z")
        if not world.terrain.is_walkable(target.x, target.z):
            return Err("that position is water or out of bounds")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """None, ever: only a plan chooses this, never the utility brain."""
        return []

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Record the destination."""
        target = params if isinstance(params, MoveToParams) else MoveToParams(x=0.0, z=0.0)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"x": target.x, "z": target.z},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Steer towards the destination until arrival or timeout."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        target = (float(run.state["x"]), float(run.state["z"]))

        if steer_towards(agent, target):
            return SkillStatus.DONE
        if run.elapsed > MOVE_TO_TIMEOUT_S:
            stop(agent)
            return SkillStatus.FAILED
        return SkillStatus.RUNNING


class Flee(Skill):
    """Run away from a frightening neighbour."""

    name = "Flee"
    description = "Run away from a dangerous agent."
    category = SkillCategory.SURVIVAL
    Params = FleeParams
    visual_state = AgentState.FLEE

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require someone worth running from."""
        if self._target(agent, world, params) is None:
            return Err("nothing nearby is threatening")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Scale fear by how unsafe the agent feels and how timid it is.

        Fear yields to dying. An agent whose thirst or hunger is nearly gone
        stops caring about the glowering neighbour and goes to the water -
        without this, a crowded island panics itself to death.
        """
        if ctx.observation is not None and ctx.observation.threat_id is None:
            return []
        timidity = 1.0 - agent.traits.courage
        desperation = max(
            need_urgency(agent.needs.thirst),
            need_urgency(agent.needs.hunger),
        )
        # One consideration, not two: desperation *discounts* the fear, and two
        # considerations would be added instead. Timidity is the weight because
        # it can exceed 1 and `apply_curve` clamps the value.
        return [
            Consideration(
                "afraid",
                need_urgency(agent.needs.safety) * max(0.0, 1.0 - desperation),
                0.45 + 0.75 * timidity,
            )
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Remember who we are running from."""
        threat = self._target(agent, world, params)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"threat": -1 if threat is None else threat.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Sprint away for a few seconds, then calm down."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        agent.needs.safety = max(0.0, agent.needs.safety - balance.SAFETY_RECOVERY * dt * 2.0)

        if run.elapsed >= balance.FLEE_DURATION:
            stop(agent)
            return SkillStatus.DONE

        threat = world.agents.get(int(run.state["threat"]))
        if threat is None or not threat.alive:
            stop(agent)
            return SkillStatus.DONE
        if distance_to(agent, threat.position) > balance.VISION_RADIUS:
            stop(agent)
            return SkillStatus.DONE

        steer_away(agent, threat.position)
        return SkillStatus.RUNNING

    @staticmethod
    def _target(agent: Agent, world: World, params: BaseModel) -> Agent | None:
        """Resolve the threat: the named agent, or the nearest scary one."""
        if isinstance(params, FleeParams) and params.from_agent is not None:
            candidate = world.agents.get(params.from_agent)
            return candidate if candidate is not None and candidate.alive else None
        return nearest_threat(world, agent)
