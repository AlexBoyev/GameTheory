"""The deliberative layer inside the tick (SPEC 7.2, ADR 0004).

The guarantee under test is that deliberation is a *bias* and an *option*:
the world ticks identically whether a model answers, answers late, answers
about a world that no longer exists, or never answers at all.
"""

from app.ai.brains.base import DecisionContext
from app.ai.brains.utility_brain import UtilityBrain
from app.ai.llm.broker import Delivery, IntentionBroker
from app.ai.llm.schemas import Intention, Reflection
from app.ai.memory import MemoryEvent
from app.ai.minds import MindRegistry
from app.ai.prompting import build_intention_context
from app.ai.skills.registry import SkillRegistry
from app.ai.systems.decision_system import INTENTION_BONUS
from app.ai.systems.intention_system import IntentionSystem
from app.sim.entities import Agent, BrainType
from app.sim.events import EventType
from app.sim.world import World


def an_intention(
    goal: str = "lead them", skill: str = "FoundTribe", say: str | None = None
) -> Intention:
    """A plan naming one skill."""
    return Intention(
        thought="They would follow me.",
        goal=goal,
        plan=[{"skill": skill, "params": {}}],  # type: ignore[list-item]
        say=say,
    )


def a_deliberate_agent(world: World, minds: MindRegistry) -> Agent:
    """The first agent, and *only* that one, on the deliberative brain.

    The default world ships four, so a test about one agent has to say so.
    """
    for other in world.living_agents():
        other.brain_type = BrainType.UTILITY
    agent = world.living_agents()[0]
    agent.brain_type = BrainType.LLM
    agent.position = (0.0, 0.0)
    world.agent_index.insert(agent.id, 0.0, 0.0)
    minds.require(agent.id)
    return agent


def a_system(
    minds: MindRegistry, skills: SkillRegistry, broker: IntentionBroker
) -> IntentionSystem:
    """An intention system that will post on the very first tick."""
    return IntentionSystem(minds, skills, broker, interval_s=0.0, lifetime_s=45.0)


# ------------------------------------------------------------------ posting


def test_only_deliberative_agents_are_asked(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """Asking a model about all 120 agents would be the bottleneck itself."""
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)

    a_system(minds, skills, broker).step(world, world.clock.dt)

    posted = broker.take_pending(limit=10)
    assert [item.context.agent_id for item in posted] == [agent.id]


def test_an_agent_is_not_asked_again_while_it_is_waiting(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)

    system.step(world, world.clock.dt)
    system.step(world, world.clock.dt)

    assert broker.pending_count == 1


def test_posting_is_capped_per_tick(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """A burst of deliberative agents must not flood the queue in one tick."""
    broker = IntentionBroker()
    for agent in world.living_agents():
        agent.brain_type = BrainType.UTILITY
    for agent in world.living_agents()[:5]:
        agent.brain_type = BrainType.LLM
        minds.require(agent.id)
    system = IntentionSystem(minds, skills, broker, interval_s=0.0, max_posts=2)

    system.step(world, world.clock.dt)

    assert broker.pending_count == 2


def test_the_prompt_context_carries_no_live_objects(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """Everything crossing to the event loop must survive the world changing."""
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)

    context = build_intention_context(world, agent, mind.memory, mind.observation, skills)

    assert context.context["agent"]["name"] == agent.name
    assert isinstance(context.context["agent"]["traits"]["charisma"], float)
    assert all(
        isinstance(value, (str, int, float, bool, list, dict, type(None)))
        for value in context.context.values()
    )


def test_only_skills_that_would_actually_run_are_offered(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """Offering an impossible action teaches the model to plan no-ops."""
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    agent.inventory.food = 0.0

    context = build_intention_context(world, agent, mind.memory, mind.observation, skills)

    offered = {entry["name"] for entry in context.context["skills"]}
    assert offered, "an agent should always have something it can do"
    assert "Eat" not in offered, "it is carrying no food"


# --------------------------------------------------------------- installing


def test_a_returned_plan_is_installed_on_the_mind(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid, intention=an_intention()))

    system.step(world, world.clock.dt)

    mind = minds.require(agent.id)
    assert mind.intention is not None
    assert mind.intention.goal == "lead them"
    assert agent.goal == "lead them"
    assert agent.thought == "They would follow me."


def test_a_plan_for_a_world_that_no_longer_exists_is_dropped(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """A reset mid-flight must not plant one world's plan in another."""
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid + 999, intention=an_intention()))

    system.step(world, world.clock.dt)

    assert minds.require(agent.id).intention is None


def test_a_plan_for_a_dead_agent_is_dropped(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    agent.alive = False
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid, intention=an_intention()))

    system.step(world, world.clock.dt)

    assert minds.require(agent.id).intention is None


def test_a_failed_deliberation_changes_nothing(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid, error="circuit open"))

    system.step(world, world.clock.dt)

    assert minds.require(agent.id).intention is None


def test_a_reflection_becomes_durable_beliefs(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(
        Delivery(
            agent_id=agent.id,
            world_uid=world.uid,
            reflection=Reflection(beliefs=["Rex steals - avoid him"], summary="Hard days."),
        )
    )

    system.step(world, world.clock.dt)

    assert minds.require(agent.id).memory.beliefs == ["Rex steals - avoid him"]


def test_a_spoken_line_becomes_a_speech_event(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(
        Delivery(
            agent_id=agent.id,
            world_uid=world.uid,
            intention=an_intention(say="Someone has to decide."),
        )
    )

    system.step(world, world.clock.dt)

    speech = [event for event in world.events.drain() if event.type is EventType.SPEECH]
    assert len(speech) == 1
    assert speech[0].data["text"] == "Someone has to decide."
    assert speech[0].actors == (agent.id,)


def test_a_silent_plan_says_nothing(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.deliver(
        Delivery(agent_id=agent.id, world_uid=world.uid, intention=an_intention(say=None))
    )

    system.step(world, world.clock.dt)

    assert not [event for event in world.events.drain() if event.type is EventType.SPEECH]


# ------------------------------------------------------------------- expiry


def test_a_plan_expires_rather_than_steering_forever(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """The world it was formed in is gone after a minute; so is the plan."""
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = IntentionSystem(minds, skills, broker, interval_s=0.0, lifetime_s=10.0)
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid, intention=an_intention()))
    system.step(world, world.clock.dt)
    mind = minds.require(agent.id)
    assert mind.active_intention(world.clock.sim_seconds) is not None

    assert mind.active_intention(world.clock.sim_seconds + 11.0) is None
    assert mind.intention is None, "an expired plan is cleared, not just hidden"


# -------------------------------------------------------------------- bias


def test_an_intention_biases_the_choice_without_overriding_it(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """A plan nudges; it does not command (SPEC 7.2)."""
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    brain = UtilityBrain(skills, temperature=0.01)

    def decide(intention_skills: tuple[str, ...]) -> dict[str, float]:
        decision = brain.decide(
            DecisionContext(
                agent=agent,
                world=world,
                memory=mind.memory,
                observation=mind.observation,
                intention_skills=intention_skills,
                intention_bonus=INTENTION_BONUS if intention_skills else 0.0,
            )
        )
        return {option.skill: option.score for option in decision.options}

    plain = decide(())
    target = next(iter(plain))
    biased = decide((target,))

    assert biased[target] == plain[target] + INTENTION_BONUS


def test_a_desperate_need_still_beats_the_plan(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """A starving schemer eats first - the whole point of bias over override."""
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    agent.needs.thirst = 1.0
    agent.needs.hunger = 1.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(
        DecisionContext(
            agent=agent,
            world=world,
            memory=mind.memory,
            observation=mind.observation,
            intention_skills=("Wander",),
            intention_bonus=INTENTION_BONUS,
        )
    )

    assert decision.skill != "Wander", f"chose {decision.skill} over surviving"


# -------------------------------------------------------------- reflection


def test_reflection_is_triggered_by_a_life_not_a_timer(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """An agent nothing happens to never pays for the expensive call."""
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    system = IntentionSystem(minds, skills, broker, interval_s=0.0, reflect_every=3)

    system.step(world, world.clock.dt)
    assert broker.take_pending()[0].context.kind == "intention"
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid))

    for index in range(3):
        mind.memory.remember(
            MemoryEvent(
                tick=index,
                sim_seconds=float(index),
                type=EventType.COMBAT,
                summary="a fight",
                importance=8,
            )
        )
    system.step(world, world.clock.dt)

    assert broker.take_pending()[0].context.kind == "reflection"


def test_unimportant_days_do_not_trigger_a_reflection(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    system = IntentionSystem(minds, skills, broker, interval_s=0.0, reflect_every=3)

    for index in range(10):
        mind.memory.remember(
            MemoryEvent(
                tick=index,
                sim_seconds=float(index),
                type=EventType.SPEECH,
                summary="walked about",
                importance=2,
            )
        )
    system.step(world, world.clock.dt)

    assert broker.take_pending()[0].context.kind == "intention"


def test_a_failed_reflection_is_not_retried_forever(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """Otherwise an unreachable model starves the agent of intentions."""
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    mind = minds.require(agent.id)
    system = IntentionSystem(minds, skills, broker, interval_s=0.0, reflect_every=2)
    for index in range(2):
        mind.memory.remember(
            MemoryEvent(
                tick=index,
                sim_seconds=float(index),
                type=EventType.DEATH,
                summary="a death",
                importance=9,
            )
        )

    system.step(world, world.clock.dt)
    assert broker.take_pending()[0].context.kind == "reflection"
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid, error="circuit open"))

    system.step(world, world.clock.dt)

    assert broker.take_pending()[0].context.kind == "intention", "it should move on"


# ------------------------------------------------------- the speed policy


def test_the_speed_policy_can_stop_deliberation_entirely(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """At MAX speed with the `off` policy, nobody is asked anything.

    The world must never slow down to wait for a model, so above the speed
    threshold deliberation thins out or stops - decided by the service, which
    is the only place that knows the engine's speed.
    """
    broker = IntentionBroker()
    a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.set_interval(None)

    system.step(world, world.clock.dt)

    assert broker.pending_count == 0


def test_the_speed_policy_can_stretch_the_interval(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    broker = IntentionBroker()
    agent = a_deliberate_agent(world, minds)
    system = a_system(minds, skills, broker)
    broker.set_interval(1000.0)

    system.step(world, world.clock.dt)
    assert broker.pending_count == 1, "the first deliberation is always due"
    broker.take_pending()
    broker.deliver(Delivery(agent_id=agent.id, world_uid=world.uid))
    system.step(world, world.clock.dt)

    assert broker.pending_count == 0, "1000 sim-seconds have not passed"


def test_an_unconfigured_broker_uses_the_system_default(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """A unit test, or the moment before the first broadcast, still works."""
    broker = IntentionBroker()
    a_deliberate_agent(world, minds)

    a_system(minds, skills, broker).step(world, world.clock.dt)

    assert broker.pending_count == 1
