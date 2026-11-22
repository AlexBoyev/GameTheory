"""Cheap truths about an agent, computed once per decision.

The utility brain scores every registered skill on every decision; most of
them are ruled out before any arithmetic. These are the facts that rule them
out, and they are deliberately free: three field reads and one list that
perception already built.

See `ai.skills.base.Requirement` for the contract these satisfy - an unmet
requirement must imply a failing `check()`, never a new condition.
"""

from app.ai.perception import Observation
from app.ai.skills.base import Requirement
from app.sim.entities import Agent, TribeRole


def agent_facts(agent: Agent, observation: Observation | None) -> frozenset[str]:
    """Return the requirements this agent currently satisfies.

    When there is no observation yet (an agent's very first tick) every fact
    that depends on one is assumed **true**: the cost of scoring a skill that
    cannot run is a wasted `check()`, while the cost of skipping one that
    could is an agent that never acts.
    """
    facts: set[str] = set()

    if observation is None or observation.visible_agents:
        facts.add(Requirement.NEARBY_AGENTS.value)

    if agent.tribe_id is None:
        facts.add(Requirement.TRIBELESS.value)
    else:
        facts.add(Requirement.IN_TRIBE.value)
        if agent.role is TribeRole.LEADER:
            facts.add(Requirement.TRIBE_LEADER.value)

    return frozenset(facts)
