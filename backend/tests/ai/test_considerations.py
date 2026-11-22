"""Considerations: the declarative form of a skill's score (SPEC 7.4).

The conversion from hand-rolled arithmetic to named inputs has to be
*algebraically* identical, and the only way to know is to write the original
formula out again here and compare. Comparing a whole world before and after
does not work: a last-bit difference changes one softmax draw, which changes
every subsequent decision, so everything differs and nothing is learned. (It
did find a real bug though - `apply_curve` clamps the value to [0, 1], so
three skills that passed a value of up to 1.4 were silently scoring 1.0. The
magnitude belongs in the weight, which is not clamped.)
"""

import pytest

from app.ai.brains.base import DecisionContext
from app.ai.brains.curves import Curve
from app.ai.minds import MindRegistry
from app.ai.perception import Observation
from app.ai.skills.base import Consideration, Skill
from app.ai.skills.registry import SkillRegistry
from app.sim import balance
from app.sim.entities import Agent, Traits
from app.sim.systems import SystemPipeline
from app.sim.world import World

TOLERANCE = 1e-12
"""Reordered floating-point multiplication is equal to about this."""


def need_urgency(value: float) -> float:
    """The same shaping the skills use, written out independently."""
    from app.ai.skills.helpers import need_urgency as real

    return real(value)


def context(
    world: World,
    agent: Agent,
    minds: MindRegistry,
    observation: Observation | None = None,
) -> DecisionContext:
    """A decision context for one agent."""
    mind = minds.require(agent.id)
    return DecisionContext(
        agent=agent,
        world=world,
        memory=mind.memory,
        observation=observation if observation is not None else mind.observation,
    )


# ------------------------------------------------------------ the mechanism


def test_a_consideration_is_value_times_weight() -> None:
    assert Consideration("x", 0.5, 2.0).score == pytest.approx(1.0)


def test_a_curve_shapes_the_value_before_weighting() -> None:
    quadratic = Consideration("x", 0.5, 1.0, Curve.QUADRATIC)

    assert quadratic.score == pytest.approx(0.25)


def test_a_value_above_one_is_clamped() -> None:
    """The trap that broke three skills: put magnitude in the weight."""
    assert Consideration("x", 1.4, 1.0).score == pytest.approx(1.0)
    assert Consideration("x", 1.0, 1.4).score == pytest.approx(1.4)


def test_a_negative_value_is_clamped_to_zero() -> None:
    assert Consideration("x", -3.0, 1.0).score == 0.0


def test_utility_sums_the_considerations(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    for skill in skills.all():
        inputs = skill.considerations(agent, ctx)
        if not inputs:
            continue
        assert skill.utility(agent, ctx) == pytest.approx(sum(item.score for item in inputs)), type(
            skill
        ).name


def test_every_skill_scores_itself_somehow(skills: SkillRegistry) -> None:
    """`utility` is no longer abstract, so a skill could define neither."""
    for skill in skills.all():
        definition = type(skill)
        overrides_utility = definition.utility is not Skill.utility
        overrides_considerations = definition.considerations is not Skill.considerations
        assert overrides_utility or overrides_considerations, (
            f"{definition.name} would silently score 0 forever"
        )


# ------------------------------------------- the converted skills, verified


def test_gather_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    gather = skills.require("Gather")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    for hunger, food, greed in [
        (100.0, 0.0, 0.5),
        (40.0, 2.0, 0.9),
        (5.0, 0.0, 0.1),
        (70.0, 10.0, 0.5),
    ]:
        agent.needs.hunger = hunger
        agent.inventory.food = food
        agent.traits = Traits(greed=greed)
        stock = min(1.0, food / balance.CARRY_TARGET)
        expected = 0.6 * need_urgency(hunger) + 0.3 * (1.0 - stock) * (0.4 + greed)

        assert gather.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_eat_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    eat = skills.require("Eat")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.inventory.food = 0.0
    assert eat.utility(agent, ctx) == 0.0, "nothing to eat scores nothing"

    agent.inventory.food = 3.0
    for hunger in (100.0, 55.0, 10.0, 0.0):
        agent.needs.hunger = hunger

        assert eat.utility(agent, ctx) == pytest.approx(need_urgency(hunger) * 1.25, abs=TOLERANCE)


def test_drink_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    drink = skills.require("Drink")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    for thirst in (100.0, 60.0, 20.0, 0.0):
        agent.needs.thirst = thirst

        assert drink.utility(agent, ctx) == pytest.approx(need_urgency(thirst) * 1.4, abs=TOLERANCE)


def test_sleep_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.sustenance import NIGHT_SLEEP_BONUS, world_is_night

    sleep = skills.require("Sleep")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)
    bonus = NIGHT_SLEEP_BONUS if world_is_night(ctx) else 0.0

    for energy in (100.0, 50.0, 5.0):
        agent.needs.energy = energy
        expected = need_urgency(energy) * (0.8 + bonus)

        assert sleep.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_flee_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """The skill where the clamping bug actually bit: fear can exceed 1."""
    flee = skills.require("Flee")
    agent = world.living_agents()[0]
    observation = Observation(tick=0, agent_id=agent.id, threat_id=99)
    ctx = context(world, agent, minds, observation=observation)

    for safety, courage, thirst, hunger in [
        (10.0, 0.0, 100.0, 100.0),  # terrified, timid, comfortable: fear > 1
        (10.0, 1.0, 100.0, 100.0),  # terrified but brave
        (10.0, 0.0, 5.0, 100.0),  # terrified and dying of thirst
        (90.0, 0.5, 100.0, 100.0),  # safe
    ]:
        agent.needs.safety = safety
        agent.needs.thirst = thirst
        agent.needs.hunger = hunger
        agent.traits = Traits(courage=courage)

        timidity = 1.0 - courage
        fear = need_urgency(safety) * (0.45 + 0.75 * timidity)
        desperation = max(need_urgency(thirst), need_urgency(hunger))
        expected = fear * max(0.0, 1.0 - desperation)

        assert flee.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE), (
            f"safety={safety} courage={courage}"
        )


def test_gather_wood_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    wood = skills.require("GatherWood")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)
    agent.inventory.wood = 0.0

    for hunger, thirst, loyalty in [(100.0, 100.0, 1.0), (80.0, 60.0, 0.2), (40.0, 100.0, 0.5)]:
        agent.needs.hunger = hunger
        agent.needs.thirst = thirst
        agent.traits = Traits(loyalty=loyalty)
        comfort = min(hunger, thirst) / balance.NEED_MAX
        expected = 0.0 if comfort < 0.5 else 0.3 * comfort * (0.4 + loyalty)

        assert wood.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_build_shelter_needs_the_wood(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    build = skills.require("BuildShelter")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.inventory.wood = 0.0
    assert build.utility(agent, ctx) == 0.0

    agent.inventory.wood = 100.0
    assert build.utility(agent, ctx) == pytest.approx(0.65)


def test_wander_is_the_floor(world: World, minds: MindRegistry, skills: SkillRegistry) -> None:
    """Any real need must outrank doing nothing."""
    from app.ai.skills.movement import WANDER_UTILITY

    wander = skills.require("Wander")
    agent = world.living_agents()[0]

    assert wander.utility(agent, context(world, agent, minds)) == pytest.approx(WANDER_UTILITY)


# ------------------------------------------------------------- the trace


def test_the_converted_skills_name_their_reasons(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """The whole point: "thirsty 0.82" explains a choice, "1.15" does not."""
    agent = world.living_agents()[0]
    agent.needs.thirst = 20.0
    ctx = context(world, agent, minds)

    named = {
        item.name
        for name in ("Gather", "Eat", "Drink", "Sleep", "Wander")
        for item in skills.require(name).considerations(agent, ctx)
    }

    assert "thirsty" in named
    assert "hungry" in named
    assert all(name and not name[0].isupper() for name in named), named


def test_the_explanation_adds_up_to_the_score(
    world: World, minds: MindRegistry, skills: SkillRegistry, pipeline: SystemPipeline
) -> None:
    """An explanation whose parts do not sum to the total is worse than none.

    This caught a real omission: the brain adds a commitment bonus to whatever
    an agent is already doing, so `BuildShelter` showed 0.90 against a single
    listed input of 0.65 and the missing 0.25 was unexplained.
    """
    for _ in range(300):
        pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()

    checked = 0
    for agent in world.living_agents():
        for option in minds.require(agent.id).trace:
            if not option.because:
                continue  # a skill that scores itself directly, not decomposed
            checked += 1
            assert option.score == pytest.approx(
                sum(score for _, score in option.because), abs=0.001
            ), f"{option.skill}: {option.score} != {option.because}"

    assert checked > 0, "no decomposed options in the sample, so this proved nothing"


def test_the_bonuses_are_named_in_the_explanation(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.brains.utility_brain import UtilityBrain

    agent = world.living_agents()[0]
    agent.needs.thirst = 10.0
    mind = minds.require(agent.id)
    brain = UtilityBrain(skills, temperature=0.01)

    decision = brain.decide(
        DecisionContext(
            agent=agent,
            world=world,
            memory=mind.memory,
            observation=mind.observation,
            current_skill="Drink",
            commitment_bonus=0.25,
            intention_skills=("Drink",),
            intention_bonus=0.35,
        )
    )

    drink = next(option for option in decision.options if option.skill == "Drink")
    named = dict(drink.because)
    assert named["already doing it"] == pytest.approx(0.25)
    assert named["it is the plan"] == pytest.approx(0.35)
    assert drink.score == pytest.approx(sum(named.values()), abs=0.001)
