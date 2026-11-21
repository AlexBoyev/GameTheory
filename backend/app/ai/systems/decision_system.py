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

INTENTION_BONUS = 0.35
"""Score added to the skills an LLM plan asked for.

A bias, never an override (SPEC 7.2): it is large enough to break a tie
between comparable options and to make a schemer follow through, and small
enough that a starving agent still eats instead of executing its plan. The
whole deliberative layer is therefore safe to switch off mid-run.
"""

COMMITMENT_BONUS = 0.25
"""Score added to whatever an agent is already doing, during a review.

Pure utility AI has no memory of having decided anything, so it re-litigates
every three seconds and abandons any errand longer than that. Agents walked
towards distant trees for days and never once arrived with enough wood to
build. A little inertia is both more realistic and more competent - and a
genuinely urgent need still outscores it easily.
"""


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
        intention = mind.active_intention(now)
        return DecisionContext(
            agent=agent,
            world=world,
            memory=mind.memory,
            observation=mind.observation,
            unavailable=unavailable,
            current_skill=mind.run.skill if mind.run is not None else None,
            commitment_bonus=COMMITMENT_BONUS if mind.run is not None else 0.0,
            intention_skills=intention.skills if intention is not None else (),
            intention_bonus=INTENTION_BONUS if intention is not None else 0.0,
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
        # The cooldown starts when the skill *finishes* (SkillExecutionSystem),
        # never here. Starting it now marked the running skill unavailable at
        # the very next review, so the agent dropped it and started something
        # else - which made any skill with a cooldown longer than the review
        # interval impossible to complete. Nobody ever finished a shelter.

        agent.current_skill = definition.name
        agent.state = definition.visual_state
        agent.intent = decision.skill
        agent.thought = decision.reason
