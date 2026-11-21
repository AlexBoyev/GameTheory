"""Keeping tribes honest: camps, territory, leadership and dissolution.

Tribes are *founded* by agents (the `FoundTribe` skill) rather than assigned
here. This system does the bookkeeping that follows: where the camp is, how
far the territory reaches, who leads, and when a tribe has shrunk to the
point that it no longer exists.

It also runs the seasonal Public Goods game, which is the one moment the
whole tribe's contributions and free-riding get settled at once.
"""

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.ai.skills.tribe import legitimacy
from app.sim.entities import Tribe, TribeRole
from app.sim.events import EventType, SimEvent
from app.sim.world import World

REVIEW_INTERVAL_TICKS = 100
"""Tribe bookkeeping is cheap but not free; twice per sim-minute is plenty."""

MIN_TRIBE_SIZE = 2
TERRITORY_PADDING = 8.0
MAX_TERRITORY = 60.0
LEADER_REVIEW_MARGIN = 0.2
REDISTRIBUTION_SHARE = 0.6
"""How much of the store is handed back out each season."""


class TribeSystem:
    """Maintains camps, territory, leadership and the seasonal share-out."""

    name = "tribes"

    __slots__ = ("_last_season", "_ledger", "_minds")

    def __init__(self, minds: MindRegistry, ledger: SocialLedger) -> None:
        self._minds = minds
        self._ledger = ledger
        self._last_season: str | None = None

    def on_world_replaced(self, world: World) -> None:
        """Nothing cached but the season marker."""
        self._last_season = None

    def step(self, world: World, dt: float) -> None:
        """Review every tribe, and settle the common store when a season turns."""
        season = world.clock.season
        season_turned = self._last_season is not None and season != self._last_season
        self._last_season = season

        if world.clock.tick % REVIEW_INTERVAL_TICKS != 0 and not season_turned:
            return

        for tribe_id in sorted(world.tribes):
            tribe = world.tribes.get(tribe_id)
            if tribe is None:
                continue
            self._prune(world, tribe)
            if tribe.id not in world.tribes:
                continue
            self._reposition(world, tribe)
            self._review_leader(world, tribe)
            if season_turned:
                self._redistribute(world, tribe)

    # ------------------------------------------------------------ internals

    def _prune(self, world: World, tribe: Tribe) -> None:
        """Drop dead members, and dissolve a tribe that has run out of people."""
        tribe.member_ids = {
            member_id
            for member_id in tribe.member_ids
            if (agent := world.agents.get(member_id)) is not None and agent.alive
        }

        if tribe.size >= MIN_TRIBE_SIZE:
            return

        for member_id in tribe.member_ids:
            member = world.agents.get(member_id)
            if member is not None:
                member.tribe_id = None
                member.role = TribeRole.NONE
        world.tribes.pop(tribe.id, None)
        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRIBE_SPLIT,
                summary=f"{tribe.name} dwindled away",
                importance=6,
                position=tribe.camp_position,
                data={"tribe": tribe.id},
            )
        )

    @staticmethod
    def _reposition(world: World, tribe: Tribe) -> None:
        """Camp sits at the members' centre; territory covers their spread."""
        members = [world.agents[m] for m in sorted(tribe.member_ids) if m in world.agents]
        if not members:
            return

        centre_x = sum(member.position[0] for member in members) / len(members)
        centre_z = sum(member.position[1] for member in members) / len(members)
        tribe.camp_position = (centre_x, centre_z)

        spread = max(
            (
                ((member.position[0] - centre_x) ** 2 + (member.position[1] - centre_z) ** 2) ** 0.5
                for member in members
            ),
            default=0.0,
        )
        tribe.territory_radius = min(MAX_TERRITORY, spread + TERRITORY_PADDING)

    def _review_leader(self, world: World, tribe: Tribe) -> None:
        """Replace a leader who is dead, gone, or clearly less legitimate."""
        members = [world.agents[m] for m in sorted(tribe.member_ids) if m in world.agents]
        if not members:
            return

        leader = world.agents.get(tribe.leader_id) if tribe.leader_id is not None else None
        if leader is None or not leader.alive or leader.tribe_id != tribe.id:
            best = max(members, key=lambda a: legitimacy(world, a, tribe, self._minds))
            tribe.leader_id = best.id
            best.role = TribeRole.LEADER
            world.events.emit(
                SimEvent(
                    tick=world.clock.tick,
                    type=EventType.LEADER_CHANGED,
                    summary=f"{best.name} now leads {tribe.name}",
                    actors=(best.id,),
                    importance=7,
                    position=tribe.camp_position,
                    data={"tribe": tribe.id},
                )
            )
            return

        # Keep roles tidy: exactly one leader.
        for member in members:
            if member.id != tribe.leader_id and member.role is TribeRole.LEADER:
                member.role = TribeRole.MEMBER
        leader.role = TribeRole.LEADER

    def _redistribute(self, world: World, tribe: Tribe) -> None:
        """The seasonal Public Goods pay-out (SPEC 5.1).

        What the tribe banked is multiplied and shared equally, so
        contributing was collectively right and individually expensive -
        which is exactly the tension the game is meant to create.
        """
        if tribe.storage_food <= 0 or tribe.size == 0:
            return

        pot = tribe.storage_food * REDISTRIBUTION_SHARE
        tribe.storage_food -= pot
        grown = pot * 1.7
        share = grown / tribe.size

        for member_id in sorted(tribe.member_ids):
            member = world.agents.get(member_id)
            if member is not None and member.alive:
                member.inventory.food += share

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.TRIBE_JOINED,
                summary=(f"{tribe.name} shared out {grown:.1f} food between {tribe.size} members"),
                importance=5,
                position=tribe.camp_position,
                data={"tribe": tribe.id, "shared": round(grown, 2)},
            )
        )
