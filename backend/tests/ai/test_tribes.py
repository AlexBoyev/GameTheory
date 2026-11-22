"""Tribes: founding, joining, leaving, the common store, coups and diplomacy.

SPEC section 6. These are the skills that turn a crowd into a society, and
they were the only Phase 4 category with no direct coverage (CLAUDE.md rule 6).
"""

import pytest
from pydantic import BaseModel

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.ai.skills.base import NoParams, Skill, SkillStatus
from app.ai.skills.registry import SkillRegistry
from app.ai.skills.social import TargetParams
from app.ai.skills.tribe import (
    COUP_MARGIN,
    JOIN_TRUST,
    STORE_AMOUNT,
    TAKE_AMOUNT,
    legitimacy,
)
from app.core.result import is_ok
from app.sim.entities import Agent, Traits, Tribe, TribeRole
from app.sim.events import EventType
from app.sim.tribe_identity import tribe_name
from app.sim.world import World


def place_agent(world: World, agent: Agent, position: tuple[float, float]) -> Agent:
    """Stand `agent` at `position`, keeping the neighbour index honest."""
    agent.position = position
    agent.velocity = (0.0, 0.0)
    world.agent_index.insert(agent.id, *position)
    return agent


def two_agents(world: World, minds: MindRegistry) -> tuple[Agent, Agent]:
    """Two agents standing together, each with a mind registered."""
    first, second = world.living_agents()[:2]
    place_agent(world, first, (0.0, 0.0))
    place_agent(world, second, (1.0, 0.0))
    for agent in (first, second):
        minds.require(agent.id)
    return first, second


def trusts(minds: MindRegistry, who: Agent, whom: Agent, amount: float) -> None:
    """Make `who` trust `whom` by `amount`."""
    relationship = minds.require(who.id).memory.relationship(whom.id)
    relationship.trust = amount
    relationship.interactions = 3


def run(skill: Skill, world: World, agent: Agent, params: BaseModel) -> SkillStatus:
    """Start and step a one-shot tribe skill to its conclusion."""
    started = skill.start(agent, world, params)
    return skill.step(started, world, world.clock.dt)


# -------------------------------------------------------------------- naming


def test_every_tribe_id_gets_its_own_name() -> None:
    """Two tribes called Holtclan is a bug that shipped once already."""
    names = [tribe_name(tribe_id) for tribe_id in range(200)]

    assert len(set(names)) == len(names)


def test_names_are_readable_not_hashes() -> None:
    assert tribe_name(0) == "Ashfolk"
    assert tribe_name(8) == "Ashkin"


# ------------------------------------------------------------------ founding


def test_founding_needs_charisma(world: World, skills: SkillRegistry, minds: MindRegistry) -> None:
    skill = skills.require("FoundTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.1)
    trusts(minds, follower, founder, 0.9)

    assert not is_ok(skill.check(founder, world, NoParams()))


def test_founding_needs_at_least_one_willing_follower(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    skill = skills.require("FoundTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, JOIN_TRUST - 0.1)

    assert not is_ok(skill.check(founder, world, NoParams())), "nobody trusts the founder"

    trusts(minds, follower, founder, JOIN_TRUST + 0.1)

    assert is_ok(skill.check(founder, world, NoParams()))


def test_founding_enrols_the_willing_and_crowns_the_founder(
    world: World, skills: SkillRegistry, minds: MindRegistry, ledger: SocialLedger
) -> None:
    skill = skills.require("FoundTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)

    assert run(skill, world, founder, NoParams()) is SkillStatus.DONE

    assert founder.tribe_id is not None
    tribe = world.tribes[founder.tribe_id]
    assert tribe.leader_id == founder.id
    assert founder.role is TribeRole.LEADER
    assert follower.id in tribe.member_ids
    assert follower.role is TribeRole.MEMBER
    assert ledger.tribes_founded == 1
    assert any(event.type is EventType.TRIBE_FOUNDED for event in world.events.drain())


def test_the_island_caps_the_number_of_tribes(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    """Without the cap, every charismatic agent founds a tribe of two."""
    skill = skills.require("FoundTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)
    for tribe_id in range(16):
        world.tribes[tribe_id] = Tribe(id=tribe_id, name=tribe_name(tribe_id), colour="#fff")

    assert not is_ok(skill.check(founder, world, NoParams()))


# ------------------------------------------------------------------- joining


def test_joining_requires_trusting_a_member(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    found = skills.require("FoundTribe")
    join = skills.require("JoinTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)
    run(found, world, founder, NoParams())

    outsider = world.living_agents()[2]
    place_agent(world, outsider, (2.0, 0.0))
    minds.require(outsider.id)

    assert not is_ok(join.check(outsider, world, TargetParams())), "no trust yet"

    trusts(minds, outsider, founder, JOIN_TRUST + 0.2)

    assert is_ok(join.check(outsider, world, TargetParams()))
    assert run(join, world, outsider, TargetParams()) is SkillStatus.DONE
    assert founder.tribe_id is not None
    assert outsider.id in world.tribes[founder.tribe_id].member_ids


def test_you_cannot_join_a_tribe_twice(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    found = skills.require("FoundTribe")
    join = skills.require("JoinTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)
    run(found, world, founder, NoParams())

    assert not is_ok(join.check(follower, world, TargetParams()))


# ------------------------------------------------------------------- leaving


def test_leaving_hands_the_leadership_on(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    """A tribe whose leader walks out must not keep pointing at them."""
    found = skills.require("FoundTribe")
    leave = skills.require("LeaveTribe")
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)
    run(found, world, founder, NoParams())
    tribe_id = founder.tribe_id
    assert tribe_id is not None

    assert run(leave, world, founder, NoParams()) is SkillStatus.DONE

    tribe = world.tribes[tribe_id]
    assert founder.tribe_id is None
    assert founder.role is TribeRole.NONE
    assert tribe.leader_id == follower.id, "the remaining member inherits"


def test_leaving_needs_a_tribe(world: World, skills: SkillRegistry, minds: MindRegistry) -> None:
    leave = skills.require("LeaveTribe")
    loner, _ = two_agents(world, minds)

    assert not is_ok(leave.check(loner, world, NoParams()))


# -------------------------------------------------- the store (public goods)


@pytest.fixture
def tribe_of_two(world: World, skills: SkillRegistry, minds: MindRegistry) -> tuple[Agent, Agent]:
    """A founded tribe with a leader and one member."""
    founder, follower = two_agents(world, minds)
    founder.traits = Traits(charisma=0.9)
    trusts(minds, follower, founder, 0.8)
    run(skills.require("FoundTribe"), world, founder, NoParams())
    world.events.drain()
    return founder, follower


def tribe_of(world: World, agent: Agent) -> Tribe:
    """The tribe `agent` belongs to, asserting that it has one."""
    assert agent.tribe_id is not None
    return world.tribes[agent.tribe_id]


def test_storing_food_moves_it_from_pocket_to_store(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    store = skills.require("StoreFood")
    founder, _ = tribe_of_two
    founder.inventory.food = 10.0
    tribe = tribe_of(world, founder)

    assert run(store, world, founder, NoParams()) is SkillStatus.DONE

    assert founder.inventory.food == pytest.approx(10.0 - STORE_AMOUNT)
    assert tribe.storage_food == pytest.approx(STORE_AMOUNT)


def test_contributing_earns_the_regard_of_the_tribe(
    world: World, skills: SkillRegistry, minds: MindRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    """The public-goods game only works if giving is noticed."""
    store = skills.require("StoreFood")
    founder, follower = tribe_of_two
    founder.inventory.food = 10.0
    before = minds.require(follower.id).memory.relationship(founder.id).trust

    run(store, world, founder, NoParams())

    assert minds.require(follower.id).memory.relationship(founder.id).trust > before


def test_you_cannot_give_what_you_need_yourself(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    store = skills.require("StoreFood")
    founder, _ = tribe_of_two
    founder.inventory.food = STORE_AMOUNT

    assert not is_ok(store.check(founder, world, NoParams()))


def test_taking_needs_a_stocked_store_and_an_appetite(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    take = skills.require("TakeFromStorage")
    founder, _ = tribe_of_two
    tribe = tribe_of(world, founder)
    founder.needs.hunger = 20.0

    assert not is_ok(take.check(founder, world, NoParams())), "store is empty"

    tribe.storage_food = 10.0

    assert is_ok(take.check(founder, world, NoParams()))
    assert run(take, world, founder, NoParams()) is SkillStatus.DONE
    assert tribe.storage_food == pytest.approx(10.0 - TAKE_AMOUNT)
    assert founder.inventory.food == pytest.approx(TAKE_AMOUNT)


def test_the_well_fed_do_not_raid_the_store(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    take = skills.require("TakeFromStorage")
    founder, _ = tribe_of_two
    tribe_of(world, founder).storage_food = 10.0
    founder.needs.hunger = 95.0
    founder.inventory.food = 5.0

    assert not is_ok(take.check(founder, world, NoParams()))


# --------------------------------------------------------------------- coups


def test_legitimacy_rises_with_the_trust_of_the_tribe(
    world: World, minds: MindRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    founder, follower = tribe_of_two
    tribe = tribe_of(world, founder)

    trusts(minds, follower, founder, -0.9)
    disliked = legitimacy(world, founder, tribe, minds)
    trusts(minds, follower, founder, 0.9)
    loved = legitimacy(world, founder, tribe, minds)

    assert loved > disliked


def test_a_coup_needs_a_clear_margin_not_a_tie(
    world: World, skills: SkillRegistry, minds: MindRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    """Equally legitimate challengers lose, and are remembered for trying."""
    challenge = skills.require("ChallengeLeader")
    founder, follower = tribe_of_two
    follower.traits = Traits(charisma=founder.traits.charisma)
    trusts(minds, founder, follower, 0.0)

    assert run(challenge, world, follower, NoParams()) is SkillStatus.FAILED

    assert tribe_of(world, founder).leader_id == founder.id
    coups = [event for event in world.events.drain() if event.type is EventType.COUP]
    assert coups and coups[0].data["succeeded"] is False
    assert minds.require(founder.id).memory.relationship(follower.id).trust < 0.0


def test_a_failed_coup_still_counts_as_an_attempt(
    world: World,
    skills: SkillRegistry,
    ledger: SocialLedger,
    tribe_of_two: tuple[Agent, Agent],
) -> None:
    """The charts read "coups: 0" in a world full of plotting until this split."""
    challenge = skills.require("ChallengeLeader")
    founder, follower = tribe_of_two
    follower.traits = Traits(charisma=founder.traits.charisma)

    run(challenge, world, follower, NoParams())

    assert ledger.coup_attempts == 1
    assert ledger.coups == 0, "nothing changed hands"


def test_a_more_legitimate_challenger_takes_the_tribe(
    world: World,
    skills: SkillRegistry,
    minds: MindRegistry,
    ledger: SocialLedger,
    tribe_of_two: tuple[Agent, Agent],
) -> None:
    challenge = skills.require("ChallengeLeader")
    founder, follower = tribe_of_two
    outsider = world.living_agents()[2]
    place_agent(world, outsider, (1.5, 0.0))
    minds.require(outsider.id)
    tribe = tribe_of(world, founder)
    tribe.member_ids.add(outsider.id)
    outsider.tribe_id = tribe.id

    # The third member adores the challenger and despises the leader.
    follower.traits = Traits(charisma=1.0)
    trusts(minds, outsider, follower, 1.0)
    trusts(minds, outsider, founder, -1.0)

    mine = legitimacy(world, follower, tribe, minds)
    theirs = legitimacy(world, founder, tribe, minds)
    assert mine > theirs + COUP_MARGIN, "the scenario must be a winnable coup"

    assert run(challenge, world, follower, NoParams()) is SkillStatus.DONE

    assert tribe.leader_id == follower.id
    assert follower.role is TribeRole.LEADER
    assert founder.role is TribeRole.ELDER
    assert ledger.coups == 1
    assert ledger.coup_attempts == 1


def test_a_leader_cannot_challenge_themselves(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    challenge = skills.require("ChallengeLeader")
    founder, _ = tribe_of_two

    assert not is_ok(challenge.check(founder, world, NoParams()))


def test_an_orphaned_tribe_is_inherited_without_a_fight(
    world: World, skills: SkillRegistry, tribe_of_two: tuple[Agent, Agent]
) -> None:
    """If the leader is dead, the challenge is a formality."""
    challenge = skills.require("ChallengeLeader")
    founder, follower = tribe_of_two
    founder.alive = False

    assert run(challenge, world, follower, NoParams()) is SkillStatus.DONE
    assert tribe_of(world, follower).leader_id == follower.id


# ----------------------------------------------------------------- diplomacy


def two_tribes(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> tuple[Agent, Tribe, Agent, Tribe]:
    """Two founded tribes, each with a leader and a member."""
    found = skills.require("FoundTribe")
    agents = world.living_agents()[:4]
    for index, agent in enumerate(agents):
        place_agent(world, agent, (float(index) * 60.0, 0.0))
        minds.require(agent.id)

    leaders: list[Agent] = []
    for leader, member in ((agents[0], agents[1]), (agents[2], agents[3])):
        place_agent(world, member, (leader.position[0] + 1.0, 0.0))
        leader.traits = Traits(charisma=0.9)
        trusts(minds, member, leader, 0.8)
        run(found, world, leader, NoParams())
        leaders.append(leader)

    world.events.drain()
    first, second = leaders
    return first, tribe_of(world, first), second, tribe_of(world, second)


def test_only_a_leader_may_declare_war(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    war = skills.require("DeclareWar")
    _, first, _, _ = two_tribes(world, skills, minds)
    member = world.agents[next(iter(sorted(first.member_ids - {first.leader_id})))]

    assert not is_ok(war.check(member, world, war.Params()))


def test_war_needs_a_rival_the_leader_actually_dislikes(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    """Wars are not declared on strangers - somebody has to be resented."""
    war = skills.require("DeclareWar")
    leader, _, _, second = two_tribes(world, skills, minds)

    assert not is_ok(war.check(leader, world, war.Params())), "no opinion of them yet"

    for member_id in second.member_ids:
        relationship = minds.require(leader.id).memory.relationship(member_id)
        relationship.trust = -0.8
        relationship.interactions = 3

    assert is_ok(war.check(leader, world, war.Params()))


def test_declaring_war_sets_both_tribes_against_each_other(
    world: World, skills: SkillRegistry, minds: MindRegistry, ledger: SocialLedger
) -> None:
    war = skills.require("DeclareWar")
    leader, first, _, second = two_tribes(world, skills, minds)
    first.allied_with.add(second.id)
    second.allied_with.add(first.id)
    for member_id in second.member_ids:
        relationship = minds.require(leader.id).memory.relationship(member_id)
        relationship.trust = -0.8
        relationship.interactions = 3

    assert run(war, world, leader, war.Params()) is SkillStatus.DONE

    assert second.id in first.at_war_with
    assert first.id in second.at_war_with, "war is never one-sided"
    assert second.id not in first.allied_with, "an alliance cannot survive a declaration"
    assert ledger.wars_declared == 1
    assert any(event.type is EventType.WAR_DECLARED for event in world.events.drain())


def test_peace_requires_being_at_war(
    world: World, skills: SkillRegistry, minds: MindRegistry
) -> None:
    peace = skills.require("OfferPeace")
    leader, _, _, _ = two_tribes(world, skills, minds)

    assert not is_ok(peace.check(leader, world, peace.Params()))


def test_peace_ends_the_war_for_both_sides(
    world: World, skills: SkillRegistry, minds: MindRegistry, ledger: SocialLedger
) -> None:
    peace = skills.require("OfferPeace")
    leader, first, rival, second = two_tribes(world, skills, minds)
    first.at_war_with.add(second.id)
    second.at_war_with.add(first.id)
    rival.traits = Traits(aggression=0.2)

    assert is_ok(peace.check(leader, world, peace.Params()))
    assert run(peace, world, leader, peace.Params()) is SkillStatus.DONE

    assert not first.at_war_with
    assert not second.at_war_with
    assert ledger.peace_made == 1
    assert any(event.type is EventType.PEACE_MADE for event in world.events.drain())


def test_a_warmonger_refuses_the_offer(
    world: World, skills: SkillRegistry, minds: MindRegistry, ledger: SocialLedger
) -> None:
    """Peace is not unilateral: the other leader gets to say no."""
    peace = skills.require("OfferPeace")
    leader, first, rival, second = two_tribes(world, skills, minds)
    first.at_war_with.add(second.id)
    second.at_war_with.add(first.id)
    rival.traits = Traits(aggression=0.95)

    assert run(peace, world, leader, peace.Params()) is SkillStatus.FAILED

    assert second.id in first.at_war_with, "the war goes on"
    assert ledger.peace_made == 0
