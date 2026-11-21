"""The deliberative layer's place in the tick (SPEC section 7.2).

This system is the only thing in the simulation that knows an LLM exists, and
it still never waits for one. Each tick it does three cheap things:

1. installs any deliberations that came back since the last tick,
2. expires plans that are past their lifetime,
3. posts a fresh request for whichever LLM agent is due one.

Everything slow happens on the event loop (`services.llm_pump`). If the model
is unreachable, slow, or switched off, every agent here keeps acting on
utility AI alone and the only visible difference is the absence of a thought.
"""

import structlog

from app.ai.llm.broker import IntentionBroker, PendingRequest
from app.ai.llm.schemas import Intention
from app.ai.minds import Mind, MindRegistry
from app.ai.prompting import build_intention_context, build_reflection_context
from app.ai.skills.registry import SkillRegistry
from app.sim.entities import Agent, BrainType
from app.sim.events import EventType, SimEvent
from app.sim.world import World

LOG = structlog.get_logger(__name__)

INTENTION_LIFETIME_SIM_S = 45.0
"""How long a plan keeps biasing choices before it is considered stale."""

REQUEST_INTERVAL_SIM_S = 20.0
"""Minimum sim-seconds between deliberations for one agent. The scheduler
enforces its own limits too; this one keeps the queue from filling with
requests the scheduler would only drop."""

SPEECH_IMPORTANCE = 4

REFLECT_EVERY_IMPORTANT = 8
"""Important events between reflections (SPEC 7.2).

Reflection is the expensive call - it reads a life rather than a moment - so
it is triggered by things actually happening to an agent, not by a timer. An
agent nothing happens to never pays for one.
"""


class IntentionSystem:
    """Posts deliberation requests and installs the answers."""

    name = "intention"

    __slots__ = (
        "_broker",
        "_minds",
        "_registry",
        "interval_s",
        "lifetime_s",
        "max_posts",
        "reflect_every",
    )

    def __init__(
        self,
        minds: MindRegistry,
        registry: SkillRegistry,
        broker: IntentionBroker,
        interval_s: float = REQUEST_INTERVAL_SIM_S,
        lifetime_s: float = INTENTION_LIFETIME_SIM_S,
        max_posts: int = 2,
        reflect_every: int = REFLECT_EVERY_IMPORTANT,
    ) -> None:
        self._minds = minds
        self._registry = registry
        self._broker = broker
        self.interval_s = interval_s
        self.lifetime_s = lifetime_s
        self.max_posts = max_posts
        self.reflect_every = reflect_every

    def step(self, world: World, dt: float) -> None:
        """Collect replies, expire stale plans, and post what is due."""
        now = world.clock.sim_seconds
        self._install(world, now)

        # The service sets this from the engine's speed and the configured
        # high-speed policy, so a world running at 25x can thin deliberation
        # out or stop it entirely without the simulation slowing down.
        interval = self._broker.interval(self.interval_s)
        if interval is None:
            return

        posted = 0
        for agent in world.living_agents():
            if posted >= self.max_posts:
                break
            if agent.brain_type is not BrainType.LLM:
                continue
            mind = self._minds.require(agent.id)
            # Expiry is a read of `active_intention`, which clears as it goes.
            mind.active_intention(now)
            if mind.llm_requested_s >= 0.0 and now - mind.llm_requested_s < interval:
                continue

            if self._due_a_reflection(mind):
                context = build_reflection_context(world, agent, mind.memory)
            else:
                unavailable = frozenset(
                    name for name, ready_at in mind.cooldowns.items() if ready_at > now
                )
                context = build_intention_context(
                    world,
                    agent,
                    mind.memory,
                    mind.observation,
                    self._registry,
                    unavailable,
                )
            accepted = self._broker.post(
                PendingRequest(context=context, world_uid=world.uid, issued_sim_s=now)
            )
            if accepted:
                mind.llm_requested_s = now
                posted += 1

    def _due_a_reflection(self, mind: Mind) -> bool:
        """Whether enough has happened to this agent to be worth summarising."""
        since = mind.memory.important_remembered - mind.reflected_at_important
        return since >= self.reflect_every

    def _install(self, world: World, now: float) -> None:
        """Apply deliberations that have come back, dropping stale ones."""
        for delivery in self._broker.collect():
            if delivery.world_uid != world.uid:
                # The world was rebuilt while this was in flight. Applying it
                # would put one world's plan into a different world.
                continue
            agent = world.agents.get(delivery.agent_id)
            if agent is None or not agent.alive:
                continue
            mind = self._minds.get(delivery.agent_id)
            if mind is None:
                continue
            if delivery.prompt:
                mind.last_prompt = delivery.prompt
            if delivery.response:
                mind.last_response = delivery.response

            if delivery.reflection is not None:
                mind.memory.beliefs = list(delivery.reflection.beliefs)
                mind.reflected_at_important = mind.memory.important_remembered
                continue
            if delivery.error is not None and self._due_a_reflection(mind):
                # A reflection that failed must not be retried forever: mark
                # it done, and the next N important events will ask again.
                mind.reflected_at_important = mind.memory.important_remembered
                continue
            if delivery.intention is None:
                continue

            self._adopt(world, agent, mind, delivery.intention, now)

    def _adopt(
        self,
        world: World,
        agent: Agent,
        mind: Mind,
        intention: Intention,
        now: float,
    ) -> None:
        """Install `intention` and say its line out loud, if it has one."""
        mind.set_intention(intention, now, self.lifetime_s)
        agent.goal = intention.goal
        if intention.thought:
            agent.thought = intention.thought

        if intention.say:
            world.events.emit(
                SimEvent(
                    tick=world.clock.tick,
                    type=EventType.SPEECH,
                    summary=f"{agent.name}: {intention.say}",
                    actors=(agent.id,),
                    importance=SPEECH_IMPORTANCE,
                    position=agent.position,
                    data={"text": intention.say, "goal": intention.goal},
                )
            )
