"""Tribes a world starts with, for presets like Tribal Wars (SPEC section 6).

Normally a tribe is something an agent *founds* once it has earned enough
trust, which takes sim-minutes. A preset that wants to study war between
established tribes cannot wait for that, so `WorldConfig.initial_tribes`
hands them out at build time instead.

The agents are grouped by where they already are rather than at random: a
tribe whose members are scattered across the island has no territory worth
fighting over, and its camp would sit in the sea.
"""

import numpy as np

from app.core.world_config import WorldConfig
from app.sim.entities import Tribe, TribeRole
from app.sim.tribe_identity import TRIBE_COLOURS, tribe_name
from app.sim.world import World

TERRITORY_RADIUS = 26.0
"""Starting territory. Wider than a founded tribe's, because these are meant
to be already established - and to overlap, which is what starts the wars."""

MIN_MEMBERS = 2
"""A tribe of one is a person. Below this the group is simply not formed."""


def form_initial_tribes(world: World, config: WorldConfig) -> None:
    """Group the starting population into `config.initial_tribes` tribes.

    Deterministic: membership follows from spawn positions, which the spawn
    RNG already fixed, and the leader is the most charismatic member with the
    lowest id breaking ties.
    """
    wanted = min(config.initial_tribes, len(world.agents))
    if wanted <= 0:
        return

    agents = world.living_agents()
    if len(agents) < wanted * MIN_MEMBERS:
        return

    # Sort by angle around the island's centre, then cut into equal arcs. It
    # is a crude clustering, but it gives each tribe one contiguous stretch of
    # coast, which is what makes territory and raids mean anything.
    angles = np.array([np.arctan2(agent.position[1], agent.position[0]) for agent in agents])
    order = np.argsort(angles, kind="stable")
    groups = np.array_split(order, wanted)

    for group in groups:
        if group.size < MIN_MEMBERS:
            continue
        members = [agents[int(index)] for index in group]
        leader = max(members, key=lambda agent: (agent.traits.charisma, -agent.id))

        tribe = Tribe(
            id=world.next_tribe_id,
            name=tribe_name(world.next_tribe_id),
            colour=TRIBE_COLOURS[world.next_tribe_id % len(TRIBE_COLOURS)],
            leader_id=leader.id,
            camp_position=(
                float(np.mean([agent.position[0] for agent in members])),
                float(np.mean([agent.position[1] for agent in members])),
            ),
            territory_radius=TERRITORY_RADIUS,
            founded_tick=0,
        )
        world.tribes[tribe.id] = tribe
        world.next_tribe_id += 1

        for member in members:
            member.tribe_id = tribe.id
            member.role = TribeRole.LEADER if member is leader else TribeRole.MEMBER
            tribe.member_ids.add(member.id)
