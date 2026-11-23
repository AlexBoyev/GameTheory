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
from app.sim.entities import Agent, Traits, Tribe, TribeRole
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
                continue  # scored nothing: no inputs applied, nothing to explain
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


# ------------------------------------------- the social half, verified too


def seen(
    world: World,
    agent: Agent,
    minds: MindRegistry,
    *others: Agent,
    threat: int | None = None,
) -> DecisionContext:
    """A context in which `agent` can see `others` (and maybe a threat)."""
    observation = Observation(
        tick=0,
        agent_id=agent.id,
        visible_agents=tuple(other.id for other in others),
        threat_id=threat,
    )
    return context(world, agent, minds, observation=observation)


def alone(world: World, agent: Agent, minds: MindRegistry) -> DecisionContext:
    """A context in which `agent` can see nobody."""
    return seen(world, agent, minds)


def opinion(minds: MindRegistry, who: Agent, whom: Agent, trust: float) -> None:
    """Set what `who` thinks of `whom`."""
    minds.require(who.id).memory.relationship(whom.id).trust = trust


def test_talk_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    talk = skills.require("Talk")
    agent, other = world.living_agents()[:2]
    assert talk.utility(agent, alone(world, agent, minds)) == 0.0, "nobody to talk to"

    ctx = seen(world, agent, minds, other)
    for social, sociability in [(100.0, 1.0), (40.0, 0.3), (5.0, 0.0)]:
        agent.needs.social = social
        agent.traits = Traits(sociability=sociability)
        expected = need_urgency(social) * (0.25 + 0.6 * sociability)

        assert talk.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_share_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.social import SHARE_AMOUNT

    share = skills.require("Share")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.inventory.food = SHARE_AMOUNT
    assert share.utility(agent, ctx) == 0.0, "nothing spare to give"

    agent.inventory.food = 5.0
    for hunger, loyalty, greed in [(100.0, 1.0, 0.0), (60.0, 0.2, 0.9), (20.0, 0.5, 0.5)]:
        agent.needs.hunger = hunger
        agent.traits = Traits(loyalty=loyalty, greed=greed)
        generosity = loyalty * 0.5 + (1.0 - greed) * 0.5
        expected = 0.35 * generosity * (hunger / balance.NEED_MAX)

        assert share.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_propose_alliance_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    propose = skills.require("ProposeAlliance")
    agent, other = world.living_agents()[:2]
    opinion(minds, agent, other, 0.8)

    assert propose.utility(agent, alone(world, agent, minds)) == 0.0, "friend out of sight"

    ctx = seen(world, agent, minds, other)
    for sociability in (0.0, 0.4, 1.0):
        agent.traits = Traits(sociability=sociability)

        assert propose.utility(agent, ctx) == pytest.approx(
            0.8 * 0.5 * (0.4 + sociability), abs=TOLERANCE
        )

    minds.require(agent.id).memory.relationship(other.id).is_ally = True
    assert propose.utility(agent, ctx) == 0.0, "already allied"


def test_trade_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    trade = skills.require("Trade")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.inventory.food = 1.0
    assert trade.utility(agent, ctx) == 0.0, "nothing to trade with"

    agent.inventory.food = 4.0
    for greed, sociability in [(1.0, 1.0), (0.1, 0.9), (0.5, 0.0)]:
        agent.traits = Traits(greed=greed, sociability=sociability)
        expected = 0.22 * (0.3 + greed) * (0.4 + sociability)

        assert trade.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_persuade_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    persuade = skills.require("Persuade")
    agent, other = world.living_agents()[:2]
    assert persuade.utility(agent, alone(world, agent, minds)) == 0.0

    for trust, charisma in [(-1.0, 1.0), (-0.3, 0.6), (0.9, 0.5)]:
        opinion(minds, agent, other, trust)
        agent.traits = Traits(charisma=charisma)
        ctx = seen(world, agent, minds, other)
        expected = 0.3 * charisma * (0.3 + max(0.0, -trust))

        assert persuade.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_bribe_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.manipulation import BRIBE_AMOUNT

    bribe = skills.require("Bribe")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.inventory.food = BRIBE_AMOUNT
    assert bribe.utility(agent, ctx) == 0.0, "nothing left over to bribe with"

    agent.inventory.food = 6.0
    for cunning, honesty in [(1.0, 0.0), (0.4, 0.7), (0.0, 1.0)]:
        agent.traits = Traits(cunning=cunning, honesty=honesty)

        assert bribe.utility(agent, ctx) == pytest.approx(
            0.25 * cunning * (1.0 - honesty), abs=TOLERANCE
        )


def test_betray_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    betray = skills.require("Betray")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    for hunger, greed, honesty, cunning in [
        (0.0, 1.0, 0.0, 1.0),  # starving and entirely without scruple
        (100.0, 1.0, 0.0, 1.0),  # the same character, well fed
        (50.0, 0.3, 0.8, 0.4),
    ]:
        agent.needs.hunger = hunger
        agent.traits = Traits(greed=greed, honesty=honesty, cunning=cunning)
        appetite = greed * (1.0 - honesty) * cunning
        expected = 0.55 * appetite * (0.4 + 1.0 - hunger / 100.0)

        assert betray.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_gossip_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    gossip = skills.require("Gossip")
    agent, other, third = world.living_agents()[:3]
    opinion(minds, agent, other, 0.5)

    ctx = seen(world, agent, minds, other)
    assert gossip.utility(agent, ctx) == 0.0, "one acquaintance is not enough to gossip"

    opinion(minds, agent, third, -0.5)
    for sociability, cunning in [(1.0, 1.0), (0.2, 0.8), (0.0, 0.0)]:
        agent.traits = Traits(sociability=sociability, cunning=cunning)
        expected = 0.3 * (0.45 * sociability + 0.55 * cunning)

        assert gossip.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_lie_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.deception import Lie

    lie = skills.require("Lie")
    agent, other = world.living_agents()[:2]
    ctx = seen(world, agent, minds, other)

    agent.traits = Traits(cunning=0.5, honesty=0.5)  # malice 0.25, under the floor
    assert lie.utility(agent, ctx) == 0.0

    for hunger, cunning, honesty in [(0.0, 1.0, 0.0), (100.0, 1.0, 0.0), (40.0, 0.9, 0.3)]:
        agent.needs.hunger = hunger
        agent.traits = Traits(cunning=cunning, honesty=honesty)
        malice = cunning * (1.0 - honesty)
        assert malice >= Lie.MALICE_FLOOR, "this case was meant to clear the floor"
        expected = 0.3 * malice * malice * (0.4 + 1.0 - hunger / 100.0)

        assert lie.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_attack_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.combat import Attack

    attack = skills.require("Attack")
    agent, other = world.living_agents()[:2]

    agent.traits = Traits(aggression=0.1)
    assert attack.utility(agent, seen(world, agent, minds, other)) == 0.0, "too placid"

    for hunger, aggression, courage, trust in [
        (0.0, 1.0, 1.0, -1.0),  # starving, furious, and hates the neighbour
        (100.0, 0.6, 0.5, 0.8),
        (30.0, 0.9, 0.2, -0.4),
    ]:
        agent.needs.hunger = hunger
        agent.traits = Traits(aggression=aggression, courage=courage)
        assert aggression >= Attack.MIN_AGGRESSION
        opinion(minds, agent, other, trust)
        ctx = seen(world, agent, minds, other)
        appetite = aggression * (0.3 + 0.7 * (1.0 - hunger / balance.NEED_MAX))
        expected = 0.5 * appetite * (0.3 + max(0.0, -trust)) * courage

        assert attack.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_defend_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    defend = skills.require("Defend")
    agent, other = world.living_agents()[:2]

    assert defend.utility(agent, alone(world, agent, minds)) == 0.0, "nothing to defend against"

    ctx = seen(world, agent, minds, other, threat=other.id)
    for safety, courage, aggression in [(0.0, 1.0, 1.0), (80.0, 0.5, 0.2), (20.0, 0.0, 0.7)]:
        agent.needs.safety = safety
        agent.traits = Traits(courage=courage, aggression=aggression)
        fear = 1.0 - safety / balance.NEED_MAX
        expected = 0.5 * fear * courage * (0.4 + aggression)

        assert defend.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_raid_scores_temperament_when_there_is_nothing_to_take(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    raid = skills.require("Raid")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.tribe_id = None
    assert raid.utility(agent, ctx) == 0.0, "no tribe to raid for"

    agent.tribe_id = 1  # a tribe with no enemy camp in reach
    for hunger, aggression, loyalty in [(0.0, 1.0, 1.0), (100.0, 1.0, 1.0), (50.0, 0.4, 0.8)]:
        agent.needs.hunger = hunger
        agent.traits = Traits(aggression=aggression, loyalty=loyalty)
        expected = 0.45 * aggression * loyalty * (0.3 + 1.0 - hunger / balance.NEED_MAX)

        assert raid.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_raid_wants_the_spoils(world: World, minds: MindRegistry, skills: SkillRegistry) -> None:
    """The term that makes the skill reachable at all: see its docstring."""
    from app.ai.skills.combat import Raid

    raid = skills.require("Raid")
    agent = world.living_agents()[0]
    agent.position = (0.0, 0.0)
    agent.needs.hunger = 50.0
    agent.traits = Traits(aggression=0.8, loyalty=0.5)
    ctx = context(world, agent, minds)

    world.tribes[1] = Tribe(id=1, name="Ours", colour="#fff", at_war_with={2})
    enemy = Tribe(id=2, name="Theirs", colour="#000", camp_position=(5.0, 0.0))
    world.tribes[2] = enemy
    agent.tribe_id = 1

    temperament = 0.45 * 0.8 * 0.5 * (0.3 + 0.5)
    assert raid.utility(agent, ctx) == pytest.approx(temperament, abs=TOLERANCE), (
        "an empty store is not worth raiding"
    )

    fervour = 0.8 * 0.5
    for stock in (2.0, Raid.WORTHWHILE_SPOILS, 100.0):
        enemy.storage_food = stock
        spoils = min(1.0, stock / Raid.WORTHWHILE_SPOILS)
        expected = temperament + spoils * 0.5 * (0.3 + fervour)

        assert raid.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)

    enemy.camp_position = (500.0, 500.0)
    assert raid.utility(agent, ctx) == pytest.approx(temperament, abs=TOLERANCE), (
        "spoils out of reach do not tempt"
    )


def test_reproduce_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    reproduce = skills.require("Reproduce")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.age = 30.0
    agent.needs.hunger = 50.0
    assert reproduce.utility(agent, ctx) == 0.0, "too hungry to think of children"

    agent.age = 60.0
    agent.needs.hunger = 100.0
    assert reproduce.utility(agent, ctx) == 0.0, "too old"

    agent.age = 30.0
    for hunger, thirst, sociability in [(100.0, 100.0, 1.0), (80.0, 60.0, 0.3), (55.0, 90.0, 0.5)]:
        agent.needs.hunger = hunger
        agent.needs.thirst = thirst
        agent.traits = Traits(sociability=sociability)
        comfort = min(hunger, thirst) / balance.NEED_MAX
        expected = 0.3 * comfort * (0.3 + sociability)

        assert reproduce.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_hunt_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    hunt = skills.require("HuntRabbit")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    for hunger, food, courage in [(100.0, 0.0, 1.0), (10.0, 0.0, 1.0), (10.0, 10.0, 0.0)]:
        agent.needs.hunger = hunger
        agent.inventory.food = food
        agent.traits = Traits(courage=courage)
        stock = min(1.0, food / balance.CARRY_TARGET)
        expected = need_urgency(hunger) * (0.35 + 0.65 * courage) * (1.0 - 0.6 * stock)

        assert hunt.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_move_to_never_wants_anything(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    """Only a plan picks `MoveTo`; the brain must never choose it by itself."""
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    assert skills.require("MoveTo").considerations(agent, ctx) == []
    assert skills.require("MoveTo").utility(agent, ctx) == 0.0


# ------------------------------------------------ the tribe half, verified


def test_found_tribe_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.tribe import FOUND_CHARISMA, JOIN_TRUST

    found = skills.require("FoundTribe")
    agent, other, third = world.living_agents()[:3]
    agent.tribe_id = None
    agent.traits = Traits(charisma=0.9)

    assert found.utility(agent, seen(world, agent, minds, other)) == 0.0, "no friends yet"

    opinion(minds, agent, other, JOIN_TRUST)
    opinion(minds, agent, third, JOIN_TRUST)
    ctx = seen(world, agent, minds, other, third)
    for charisma in (FOUND_CHARISMA, 0.8, 1.0):
        agent.traits = Traits(charisma=charisma)

        assert found.utility(agent, ctx) == pytest.approx(
            0.4 * charisma * min(1.0, 2.0 / 3.0), abs=TOLERANCE
        )

    agent.traits = Traits(charisma=0.2)
    assert found.utility(agent, ctx) == 0.0, "nobody would follow them"


def test_join_tribe_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    join = skills.require("JoinTribe")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.tribe_id = 1
    assert join.utility(agent, ctx) == 0.0, "already in one"

    agent.tribe_id = None
    for safety, loyalty in [(0.0, 1.0), (100.0, 1.0), (40.0, 0.2)]:
        agent.needs.safety = safety
        agent.traits = Traits(loyalty=loyalty)
        safety_pull = 1.0 - safety / balance.NEED_MAX
        expected = 0.35 * (0.4 + loyalty) * (0.3 + safety_pull)

        assert join.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_leave_tribe_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    leave = skills.require("LeaveTribe")
    agent, leader = world.living_agents()[:2]
    world.tribes[1] = Tribe(id=1, name="Test", colour="#fff", leader_id=leader.id)
    agent.tribe_id = 1
    ctx = context(world, agent, minds)

    opinion(minds, agent, leader, 0.5)
    assert leave.utility(agent, ctx) == 0.0, "a trusted leader keeps the tribe together"

    for trust, loyalty in [(-1.0, 0.0), (-0.5, 0.8), (-0.21, 0.5)]:
        opinion(minds, agent, leader, trust)
        agent.traits = Traits(loyalty=loyalty)
        expected = 0.4 * (-trust) * (1.0 - loyalty)

        assert leave.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_challenge_leader_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    challenge = skills.require("ChallengeLeader")
    agent, leader = world.living_agents()[:2]
    world.tribes[1] = Tribe(id=1, name="Test", colour="#fff", leader_id=leader.id)
    agent.tribe_id = 1
    ctx = context(world, agent, minds)

    for trust, charisma, loyalty in [(-1.0, 1.0, 0.0), (0.9, 1.0, 0.0), (-0.4, 0.6, 0.5)]:
        opinion(minds, agent, leader, trust)
        agent.traits = Traits(charisma=charisma, loyalty=loyalty)
        resentment = max(0.0, -trust)
        expected = 0.4 * charisma * (1.0 - loyalty) * (0.4 + resentment)

        assert challenge.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)

    world.tribes[1].leader_id = agent.id
    assert challenge.utility(agent, ctx) == 0.0, "nobody challenges themselves"


def test_declare_war_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    war = skills.require("DeclareWar")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.role = TribeRole.MEMBER
    assert war.utility(agent, ctx) == 0.0, "only a leader declares war"

    agent.role = TribeRole.LEADER
    for aggression, honesty in [(1.0, 0.0), (0.3, 0.9), (0.7, 0.5)]:
        agent.traits = Traits(aggression=aggression, honesty=honesty)
        expected = 0.3 * aggression * (1.0 - honesty + 0.3)

        assert war.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_offer_peace_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    peace = skills.require("OfferPeace")
    agent = world.living_agents()[0]
    tribe = Tribe(id=1, name="Test", colour="#fff", leader_id=agent.id)
    world.tribes[1] = tribe
    agent.tribe_id = 1
    agent.role = TribeRole.LEADER
    ctx = context(world, agent, minds)

    assert peace.utility(agent, ctx) == 0.0, "not at war with anyone"

    tribe.at_war_with = {2}
    for members, aggression in [(1, 0.0), (8, 0.0), (4, 0.6)]:
        tribe.member_ids = set(range(members))
        agent.traits = Traits(aggression=aggression)
        weakness = 1.0 - min(1.0, members / 8.0)
        expected = 0.35 * (1.0 - aggression) * (0.4 + weakness)

        assert peace.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)


def test_store_food_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    from app.ai.skills.tribe import STORE_AMOUNT

    store = skills.require("StoreFood")
    agent = world.living_agents()[0]
    agent.tribe_id = 1
    ctx = context(world, agent, minds)

    agent.inventory.food = STORE_AMOUNT
    assert store.utility(agent, ctx) == 0.0, "not enough to spare for the tribe"

    agent.inventory.food = 8.0
    for loyalty, greed in [(1.0, 0.0), (0.2, 0.9), (0.5, 0.5)]:
        agent.traits = Traits(loyalty=loyalty, greed=greed)

        assert store.utility(agent, ctx) == pytest.approx(
            0.4 * loyalty * (1.0 - greed), abs=TOLERANCE
        )


def test_take_from_storage_matches_the_original_formula(
    world: World, minds: MindRegistry, skills: SkillRegistry
) -> None:
    take = skills.require("TakeFromStorage")
    agent = world.living_agents()[0]
    ctx = context(world, agent, minds)

    agent.tribe_id = None
    assert take.utility(agent, ctx) == 0.0, "no store to take from"

    agent.tribe_id = 1
    for hunger, greed in [(0.0, 1.0), (100.0, 1.0), (60.0, 0.2)]:
        agent.needs.hunger = hunger
        agent.traits = Traits(greed=greed)
        expected = 0.5 * (1.0 - hunger / balance.NEED_MAX) * (0.6 + 0.4 * greed)

        assert take.utility(agent, ctx) == pytest.approx(expected, abs=TOLERANCE)
