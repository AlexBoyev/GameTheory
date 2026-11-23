"""Violence: Attack, Defend, Raid (SPEC section 7.3).

Fighting is deliberately a bad deal. Both sides get hurt, the winner takes
only what the loser was carrying, and everyone who sees it thinks worse of
the aggressor - so aggression has to be a trait, not a strategy.
"""

from pydantic import BaseModel

from app.ai import social
from app.ai.brains.base import DecisionContext
from app.ai.skills.base import (
    Consideration,
    NoParams,
    Requirement,
    Skill,
    SkillCategory,
    SkillRun,
    SkillStatus,
)
from app.ai.skills.helpers import stop
from app.ai.skills.targeting import TargetParams, nearby_agents, resolve_target
from app.core.result import OK_NONE, Err, Result
from app.sim import balance
from app.sim.entities import Agent, AgentState, DeathCause
from app.sim.events import EventType, SimEvent
from app.sim.world import World

ATTACK_DAMAGE = 14.0
DEFENDER_DAMAGE = 7.0
DEFEND_DURATION = 5.0
RAID_HAUL = 4.0


class Attack(Skill):
    """Hit someone and take what they carry."""

    name = "Attack"
    description = "Attack a nearby agent and take their food."
    category = SkillCategory.COMBAT
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = TargetParams
    visual_state = AgentState.FIGHT
    cooldown = 30.0

    MIN_AGGRESSION = 0.55

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require the temperament, the health, and a target."""
        if agent.traits.aggression < self.MIN_AGGRESSION:
            return Err("not the violent sort")
        if agent.health < 35.0:
            return Err("too hurt to fight")
        if resolve_target(world, agent, params) is None:
            return Err("nobody nearby")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Aggression plus hunger, damped by how much they like the neighbours."""
        if agent.traits.aggression < self.MIN_AGGRESSION:
            return []
        hunger = 1.0 - agent.needs.hunger / balance.NEED_MAX
        appetite = agent.traits.aggression * (0.3 + 0.7 * hunger)

        worst = 0.0
        for other_id, relationship in ctx.memory.social.items():
            if ctx.observation is not None and other_id not in ctx.observation.visible_agents:
                continue
            worst = max(worst, -relationship.trust)
        return [
            Consideration("angry and bold", appetite * agent.traits.courage, 0.5 * (0.3 + worst))
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Pick a victim - by preference, one we already dislike."""
        explicit = resolve_target(world, agent, params)
        memory = self.services.minds.require(agent.id).memory
        victim = explicit
        worst = 1.0
        for other in nearby_agents(world, agent):
            relationship = memory.social.get(other.id)
            trust = relationship.trust if relationship else 0.0
            if trust < worst:
                worst, victim = trust, other
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"victim": -1 if victim is None else victim.id},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Trade blows. The defender's courage decides how much it costs."""
        agent = world.agents[run.agent_id]
        victim = world.agents.get(int(run.state["victim"]))
        if victim is None or not victim.alive:
            return SkillStatus.FAILED

        resistance = 0.4 + 0.6 * victim.traits.courage
        victim.health = max(0.0, victim.health - ATTACK_DAMAGE)
        agent.health = max(1.0, agent.health - DEFENDER_DAMAGE * resistance)
        victim.needs.safety = 0.0
        if victim.health <= 0.0:
            victim.death_cause = DeathCause.COMBAT

        taken = victim.inventory.food
        victim.inventory.food = 0.0
        agent.inventory.food += taken

        services = self.services
        theirs = services.minds.require(victim.id).memory.relationship(agent.id)
        social.adjust_trust(theirs, social.ATTACK_TRUST)
        theirs.is_ally = False
        services.ledger.attacks += 1

        for witness in nearby_agents(world, victim):
            if witness.id == agent.id:
                continue
            belief = services.minds.require(witness.id).memory.relationship(agent.id)
            belief.reputation = social.clamp_trust(belief.reputation - 0.35)
            witness.needs.safety = max(0.0, witness.needs.safety - 30.0)

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.COMBAT,
                summary=f"{agent.name} attacked {victim.name}",
                actors=(agent.id, victim.id),
                importance=8,
                position=agent.position,
                data={"food_taken": round(taken, 2)},
            )
        )
        return SkillStatus.DONE


class Defend(Skill):
    """Stand your ground and recover your nerve."""

    name = "Defend"
    description = "Brace against a threat instead of running."
    category = SkillCategory.COMBAT
    requires = frozenset({Requirement.NEARBY_AGENTS})
    Params = NoParams
    visual_state = AgentState.FIGHT
    cooldown = 10.0

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require something to brace against."""
        if agent.needs.safety > 60.0:
            return Err("nothing to brace against")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """The brave hold; the timid run (that is `Flee`)."""
        if ctx.observation is not None and ctx.observation.threat_id is None:
            return []
        fear = 1.0 - agent.needs.safety / balance.NEED_MAX
        return [
            Consideration(
                "brave under threat",
                fear * agent.traits.courage,
                0.5 * (0.4 + agent.traits.aggression),
            )
        ]

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Plant your feet."""
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Recover composure faster than fleeing would."""
        agent = world.agents[run.agent_id]
        run.elapsed += dt
        agent.needs.safety = min(balance.NEED_MAX, agent.needs.safety + 12.0 * dt)
        return SkillStatus.DONE if run.elapsed >= DEFEND_DURATION else SkillStatus.RUNNING


class RaidParams(BaseModel):
    """Which tribe's stores to raid."""

    tribe: int | None = None


class Raid(Skill):
    """Take food from a rival tribe's storage."""

    name = "Raid"
    description = "Raid a hostile tribe's food store."
    category = SkillCategory.COMBAT
    requires = frozenset({Requirement.IN_TRIBE})
    Params = RaidParams
    visual_state = AgentState.FIGHT
    cooldown = 90.0

    RAID_RADIUS = 20.0

    WORTHWHILE_SPOILS = 6.0
    """Enemy storage at which a raid is as tempting as it ever gets."""

    def check(self, agent: Agent, world: World, params: BaseModel) -> Result[None, str]:
        """Require a tribe of your own, and an enemy camp within reach."""
        if agent.tribe_id is None:
            return Err("raiding is a tribe activity")
        if self._target_tribe(agent, world) is None:
            return Err("no enemy camp in reach")
        return OK_NONE

    def considerations(self, agent: Agent, ctx: DecisionContext) -> list[Consideration]:
        """Aggressive, loyal, hungry tribe members raid - for the spoils.

        The spoils term is why this skill is reachable at all. Without it a
        raid scored on temperament alone (median 0.056 in a measured run)
        and never once outscored gathering berries, so no raid ever happened
        in 6,000 ticks even on the handful of samples where a war, a stocked
        enemy and a raider in range all coincided.
        """
        if agent.tribe_id is None:
            return []
        hunger = 1.0 - agent.needs.hunger / balance.NEED_MAX
        fervour = agent.traits.aggression * agent.traits.loyalty
        inputs = [Consideration("aggressive and loyal", fervour, 0.45 * (0.3 + hunger))]

        target = self._target_tribe(agent, ctx.world)
        if target is not None:
            spoils = min(1.0, ctx.world.tribes[target].storage_food / self.WORTHWHILE_SPOILS)
            inputs.append(
                Consideration("their store is worth taking", spoils, 0.5 * (0.3 + fervour))
            )
        return inputs

    def _target_tribe(self, agent: Agent, world: World) -> int | None:
        """The nearest camp belonging to a tribe we are at war with."""
        own = world.tribes.get(agent.tribe_id) if agent.tribe_id is not None else None
        if own is None:
            return None
        x, z = agent.position
        for tribe_id in sorted(own.at_war_with):
            enemy = world.tribes.get(tribe_id)
            if enemy is None or enemy.storage_food <= 0:
                continue
            camp_x, camp_z = enemy.camp_position
            if (camp_x - x) ** 2 + (camp_z - z) ** 2 <= self.RAID_RADIUS**2:
                return tribe_id
        return None

    def start(self, agent: Agent, world: World, params: BaseModel) -> SkillRun:
        """Go for the stores."""
        target = self._target_tribe(agent, world)
        stop(agent)
        return SkillRun(
            skill=self.name,
            agent_id=agent.id,
            params=params,
            started_tick=world.clock.tick,
            state={"tribe": -1 if target is None else target},
        )

    def step(self, run: SkillRun, world: World, dt: float) -> SkillStatus:
        """Carry off what you can."""
        agent = world.agents[run.agent_id]
        tribe = world.tribes.get(int(run.state["tribe"]))
        if tribe is None or tribe.storage_food <= 0:
            return SkillStatus.FAILED

        haul = min(RAID_HAUL, tribe.storage_food)
        tribe.storage_food -= haul
        agent.inventory.food += haul

        minds = self.services.minds
        for member_id in sorted(tribe.member_ids):
            if member_id in world.agents:
                relationship = minds.require(member_id).memory.relationship(agent.id)
                social.adjust_trust(relationship, -0.4)

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.RAID,
                summary=f"{agent.name} raided {tribe.name} and took {haul:.1f} food",
                actors=(agent.id,),
                importance=8,
                position=agent.position,
                data={"tribe": tribe.id, "food": round(haul, 2)},
            )
        )
        return SkillStatus.DONE
