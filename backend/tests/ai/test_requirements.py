"""The contract that makes the skill gate safe to have at all.

`UtilityBrain._score_all` skips a skill whose declared `requires` are not in
the agent's facts, which removes about a quarter of all skill scoring (worth
4-8% of wall clock - the skipped `check()`s are the cheap ones).
It is only correct if an unmet requirement *implies* a failing `check()`: a
requirement is a cheap pre-test of something `check()` already enforces, never
a new condition.

Getting that wrong would silently disable a skill - no error, no failed test,
just an agent that never gossips. So the invariant is machine-checked here,
against real agents in a running world rather than against a hand-built
scenario, because the interesting cases are the ones nobody thought of.
"""

import pytest

from app.ai.facts import agent_facts
from app.ai.minds import MindRegistry
from app.ai.skills.base import Requirement, Skill
from app.ai.skills.registry import SkillRegistry
from app.core.result import is_ok
from app.sim.systems import SystemPipeline
from app.sim.world import World

TICKS = 240
"""Long enough for tribes, alliances and fights to exist in the sample."""


def declared(skills: SkillRegistry) -> list[Skill]:
    """Every skill that declares at least one requirement."""
    return [skill for skill in skills.all() if type(skill).requires]


def test_some_skills_declare_requirements(skills: SkillRegistry) -> None:
    """A guard on the guard: if the annotations vanish, the rest is vacuous."""
    assert len(declared(skills)) >= 15


def test_every_requirement_is_a_real_one(skills: SkillRegistry) -> None:
    valid = {requirement.value for requirement in Requirement}

    for skill in skills.all():
        for requirement in type(skill).requires:
            assert requirement.value in valid, f"{type(skill).name}: {requirement}"


def test_an_unmet_requirement_implies_a_failing_check(
    world: World, minds: MindRegistry, skills: SkillRegistry, pipeline: SystemPipeline
) -> None:
    """The invariant, over every agent in a world that has lived a while.

    For each agent and each skill whose requirements that agent does not
    satisfy, `check()` must also refuse. If this fails, the skill's `requires`
    is stricter than its `check()` and the brain is skipping something that
    could have run.
    """
    for _ in range(TICKS):
        pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()

    violations: list[str] = []
    examined = 0

    for agent in world.living_agents():
        facts = agent_facts(agent, minds.require(agent.id).observation)
        for skill in declared(skills):
            definition = type(skill)
            if definition.requires.issubset(facts):
                continue
            examined += 1
            params = definition.Params()
            if is_ok(skill.check(agent, world, params)):
                missing = {
                    requirement.value
                    for requirement in definition.requires
                    if requirement.value not in facts
                }
                violations.append(
                    f"{definition.name} would run for agent {agent.id} "
                    f"despite missing {sorted(missing)}"
                )

    assert examined > 0, "the sample contained no skipped skills, so this proved nothing"
    assert not violations, "\n".join(violations[:10])


def test_the_gate_actually_skips_a_useful_number(
    world: World, minds: MindRegistry, skills: SkillRegistry, pipeline: SystemPipeline
) -> None:
    """If it skips almost nothing, the complexity is not paying for itself."""
    for _ in range(TICKS):
        pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()

    total = 0
    skipped = 0
    for agent in world.living_agents():
        facts = agent_facts(agent, minds.require(agent.id).observation)
        for skill in skills.all():
            if not type(skill).autonomous:
                continue
            total += 1
            if not type(skill).requires.issubset(facts):
                skipped += 1

    share = skipped / max(1, total)
    assert share > 0.2, f"only {share:.0%} of scoring was skipped"


@pytest.mark.parametrize(
    ("skill_name", "requirement"),
    [
        ("Talk", Requirement.NEARBY_AGENTS),
        ("Gossip", Requirement.NEARBY_AGENTS),
        ("Attack", Requirement.NEARBY_AGENTS),
        ("Raid", Requirement.IN_TRIBE),
        ("StoreFood", Requirement.IN_TRIBE),
        ("FoundTribe", Requirement.TRIBELESS),
        ("DeclareWar", Requirement.TRIBE_LEADER),
    ],
)
def test_the_obvious_requirements_are_declared(
    skills: SkillRegistry, skill_name: str, requirement: Requirement
) -> None:
    """Spot-checks, so a careless edit cannot quietly drop the annotations."""
    assert requirement in type(skills.require(skill_name)).requires


def test_facts_describe_a_tribeless_agent(world: World) -> None:
    agent = world.living_agents()[0]
    agent.tribe_id = None

    facts = agent_facts(agent, None)

    assert Requirement.TRIBELESS.value in facts
    assert Requirement.IN_TRIBE.value not in facts
    assert Requirement.TRIBE_LEADER.value not in facts


def test_facts_describe_a_leader(world: World) -> None:
    from app.sim.entities import TribeRole

    agent = world.living_agents()[0]
    agent.tribe_id = 1
    agent.role = TribeRole.LEADER

    facts = agent_facts(agent, None)

    assert Requirement.IN_TRIBE.value in facts
    assert Requirement.TRIBE_LEADER.value in facts
    assert Requirement.TRIBELESS.value not in facts


def test_a_member_is_not_a_leader(world: World) -> None:
    from app.sim.entities import TribeRole

    agent = world.living_agents()[0]
    agent.tribe_id = 1
    agent.role = TribeRole.MEMBER

    facts = agent_facts(agent, None)

    assert Requirement.IN_TRIBE.value in facts
    assert Requirement.TRIBE_LEADER.value not in facts


def test_no_observation_assumes_company(world: World) -> None:
    """Absence of an observation must not be read as absence of company.

    On an agent's first tick, scoring a doomed skill costs one `check()`;
    skipping a possible one costs an agent that never acts.
    """
    agent = world.living_agents()[0]

    assert Requirement.NEARBY_AGENTS.value in agent_facts(agent, None)
