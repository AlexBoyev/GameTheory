"""Choosing what to do next, and starting it (SPEC section 7.1)."""

from app.ai.brains.base import Brain, Decision, DecisionContext
from app.ai.minds import Mind, MindRegistry
from app.ai.skills.registry import SkillRegistry
from app.core.result import is_ok
from app.sim.entities import Agent, AgentState
from app.sim.world import World

REVIEW_INTERVAL_SIM_S = 3.0
"""How often a busy agent reconsiders. Low enough to react to a new threat,
high enough that agents finish what they start instead of dithering."""


class DecisionSystem:
    """Asks the brain for a skill whenever an agent is idle or due a review."""

    name = "decision"

    __slots__ = ("_brain", "_minds", "_registry", "review_interval")

    def __init__(
        self,
        minds: MindRegistry,
        brain: Brain,
        registry: SkillRegistry,
        review_interval: float = REVIEW_INTERVAL_SIM_S,
    ) -> None:
        self._minds = minds
        self._brain = brain
        self._registry = registry
        self.review_interval = review_interval

    def step(self, world: World, dt: float) -> None:
        """Decide for every agent that needs a decision this tick."""
        now = world.clock.sim_seconds

        for agent in world.living_agents():
            mind = self._minds.require(agent.id)
            if not self._needs_decision(mind, now):
                continue

            decision = self._brain.decide(self._context(world, agent, mind, now))
            mind.last_decision_s = now

            if not decision.skill:
                continue
            if mind.run is not None and mind.run.skill == decision.skill:
                mind.trace = decision.options
                continue
            self._begin(world, agent, mind, decision, now)

    def _needs_decision(self, mind: Mind, now: float) -> bool:
        """Whether this agent should decide now."""
        if mind.run is None:
            return True
        skill = self._registry.get(mind.run.skill)
        if skill is not None and not type(skill).interruptible:
            return False
        return now - mind.last_decision_s >= self.review_interval

    def _context(self, world: World, agent: Agent, mind: Mind, now: float) -> DecisionContext:
        """Build the context the brain is allowed to see."""
        unavailable = frozenset(name for name, ready_at in mind.cooldowns.items() if ready_at > now)
        return DecisionContext(
            agent=agent,
            world=world,
            memory=mind.memory,
            observation=mind.observation,
            unavailable=unavailable,
        )

    def _begin(
        self,
        world: World,
        agent: Agent,
        mind: Mind,
        decision: Decision,
        now: float,
    ) -> None:
        """Start the chosen skill, abandoning whatever was running."""
        skill = self._registry.get(decision.skill)
        if skill is None:
            return

        definition = type(skill)
        params = definition.Params(**decision.params) if decision.params else definition.Params()
        verdict = skill.check(agent, world, params)
        if not is_ok(verdict):
            # The world moved between scoring and starting; wait for the next
            # decision rather than running a skill whose target is gone.
            mind.run = None
            agent.current_skill = None
            agent.state = AgentState.IDLE
            return

        mind.run = skill.start(agent, world, params)
        mind.trace = decision.options
        mind.reason = decision.reason
        mind.start_cooldown(definition.name, now, definition.cooldown)

        agent.current_skill = definition.name
        agent.state = definition.visual_state
        agent.intent = decision.skill
        agent.thought = decision.reason
