"""The utility brain: scoring, the trace, cooldowns and personality."""

import numpy as np

from app.ai.brains.base import DecisionContext
from app.ai.brains.utility_brain import Curve, UtilityBrain, apply_curve
from app.ai.memory import AgentMemory
from app.ai.skills.registry import SkillRegistry, build_registry
from app.sim.entities import Agent, ResourceKind
from app.sim.world import World
from tests.factories import centre_agent, clear_resources, place


def context(world: World, agent: Agent, **kwargs: object) -> DecisionContext:
    """Build a decision context with sensible defaults."""
    return DecisionContext(agent=agent, world=world, memory=AgentMemory(), **kwargs)  # type: ignore[arg-type]


def test_response_curves_stay_in_range() -> None:
    for curve in Curve:
        for value in (-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
            assert 0.0 <= apply_curve(curve, value) <= 1.0

    assert apply_curve(Curve.INVERSE, 0.0) == 1.0
    assert apply_curve(Curve.QUADRATIC, 0.5) == 0.25
    assert apply_curve(Curve.STEP, 0.49) == 0.0
    assert apply_curve(Curve.STEP, 0.5) == 1.0


def test_a_hungry_agent_with_food_decides_to_eat(world: World, skills: SkillRegistry) -> None:
    agent = centre_agent(world)
    agent.needs.hunger = 5.0
    agent.inventory.food = 2.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(context(world, agent))

    assert decision.skill == "Eat"


def test_a_thirsty_agent_next_to_water_decides_to_drink(
    world: World, skills: SkillRegistry
) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    place(world, ResourceKind.WATER, (1.0, 0.0))
    agent.needs.thirst = 5.0
    agent.needs.hunger = 100.0
    agent.needs.energy = 100.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(context(world, agent))

    assert decision.skill == "Drink"


def test_an_agent_with_nothing_to_do_wanders(world: World, skills: SkillRegistry) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    agent.needs.hunger = 100.0
    agent.needs.thirst = 100.0
    agent.needs.energy = 100.0
    agent.needs.safety = 100.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(context(world, agent))

    assert decision.skill == "Wander"


def test_the_trace_holds_the_top_three_options(world: World, skills: SkillRegistry) -> None:
    agent = centre_agent(world)
    place(world, ResourceKind.WATER, (1.0, 0.0))
    place(world, ResourceKind.BERRY_BUSH, (1.5, 0.0))
    agent.needs.hunger = 30.0
    agent.needs.thirst = 30.0
    agent.needs.energy = 30.0
    agent.inventory.food = 1.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(context(world, agent))

    assert 1 <= len(decision.options) <= 3
    scores = [option.score for option in decision.options]
    assert scores == sorted(scores, reverse=True), "the trace must be ranked"
    assert decision.reason


def test_cooldowns_are_respected(world: World, skills: SkillRegistry) -> None:
    agent = centre_agent(world)
    agent.needs.hunger = 5.0
    agent.inventory.food = 2.0
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(context(world, agent, unavailable=frozenset({"Eat"})))

    assert decision.skill != "Eat"


def test_an_intention_can_tip_a_close_decision(world: World, skills: SkillRegistry) -> None:
    agent = centre_agent(world)
    clear_resources(world)
    agent.needs.hunger = 100.0
    agent.needs.thirst = 100.0
    agent.needs.energy = 60.0
    brain = UtilityBrain(skills, temperature=0.01)

    without = brain.decide(context(world, agent))
    with_plan = brain.decide(
        context(world, agent, intention_skills=("Wander",), intention_bonus=5.0)
    )

    assert without.skill == "Sleep"
    assert with_plan.skill == "Wander"
    assert with_plan.from_intention


def test_temperature_controls_variety(world: World, skills: SkillRegistry) -> None:
    """A hot brain should not always pick the top option."""
    agent = centre_agent(world)
    place(world, ResourceKind.WATER, (1.0, 0.0))
    agent.needs.hunger = 50.0
    agent.needs.thirst = 50.0
    agent.needs.energy = 50.0
    agent.inventory.food = 1.0

    world.rngs["decide"] = np.random.default_rng(4)
    hot = UtilityBrain(skills, temperature=2.0)
    chosen = {hot.decide(context(world, agent)).skill for _ in range(40)}

    assert len(chosen) > 1, "a high temperature must produce varied choices"


def test_the_reason_never_claims_a_lower_score_beat_a_higher_one(
    world: World, skills: SkillRegistry
) -> None:
    """Softmax can pick the runner-up; the wording has to admit that.

    The inspector used to say "Flee (0.34) over Gather (0.49)", which reads as
    though 0.34 beat 0.49 - it looks like an arithmetic bug rather than a
    personality.
    """
    agent = centre_agent(world)
    place(world, ResourceKind.WATER, (1.0, 0.0))
    agent.needs.hunger = 45.0
    agent.needs.thirst = 45.0
    agent.needs.energy = 45.0
    agent.inventory.food = 1.0

    # A hot brain samples widely, so both branches of the wording show up.
    world.rngs["decide"] = np.random.default_rng(11)
    brain = UtilityBrain(skills, temperature=2.0)

    for _ in range(60):
        decision = brain.decide(context(world, agent))
        if len(decision.options) < 2:
            continue
        best, chosen = (
            decision.options[0],
            next(option for option in decision.options if option.skill == decision.skill),
        )
        if chosen.score < best.score:
            assert "passing up" in decision.reason, decision.reason
            assert " over " not in decision.reason, decision.reason
        else:
            assert " over " in decision.reason or "only option" in decision.reason


def test_decisions_are_deterministic_for_a_given_rng(world: World) -> None:
    agent = centre_agent(world)
    place(world, ResourceKind.BERRY_BUSH, (1.0, 0.0))
    agent.needs.hunger = 50.0

    first_registry = build_registry()
    second_registry = build_registry()

    world.rngs["decide"] = np.random.default_rng(99)
    first = [UtilityBrain(first_registry).decide(context(world, agent)).skill for _ in range(10)]
    world.rngs["decide"] = np.random.default_rng(99)
    second = [UtilityBrain(second_registry).decide(context(world, agent)).skill for _ in range(10)]

    assert first == second
