"""Turning a world into JSON and back (SPEC section 11).

Two decisions shape this file.

**Terrain is not stored.** It is a pure function of `config.terrain` and the
seed, so a snapshot keeps the config and regenerates the heightmap on load.
That takes a snapshot of 200 agents from megabytes to tens of kilobytes, and
the alternative - shipping a 128x128 float grid - would be storing something
we can always recompute.

**Minds are stored.** A world restored without its memories would look
identical for one tick and then behave like a world of strangers: no trust, no
grudges, no reputations. The society *is* the interesting state, so trust,
history and beliefs all go in the blob.

RNG streams are restored by re-deriving them from the seed and replaying
nothing, which means a loaded world is deterministic going forward but is not
bit-identical to the run it came from. That is an honest trade and it is
documented in the snapshot DTO.
"""

from typing import Any

from app.ai.gametheory.ledger import SocialLedger
from app.ai.memory import AgentMemory, MemoryEvent, Relationship
from app.ai.minds import MindRegistry
from app.core.world_config import WorldConfig
from app.sim.clock import SimClock
from app.sim.entities import (
    Agent,
    AgentState,
    BrainType,
    DeathCause,
    Inventory,
    LifeStage,
    Needs,
    ResourceKind,
    ResourceNode,
    Shelter,
    Traits,
    Tribe,
    TribeRole,
)
from app.sim.events import EventType
from app.sim.world import World, WorldBuilder

FORMAT_VERSION = 1
"""Bumped whenever the shape below changes incompatibly."""


# --------------------------------------------------------------------- dump


def _agent_to_dict(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "position": list(agent.position),
        "traits": {
            "aggression": agent.traits.aggression,
            "honesty": agent.traits.honesty,
            "loyalty": agent.traits.loyalty,
            "greed": agent.traits.greed,
            "sociability": agent.traits.sociability,
            "cunning": agent.traits.cunning,
            "courage": agent.traits.courage,
            "charisma": agent.traits.charisma,
        },
        "strategy": agent.strategy,
        "brain_type": agent.brain_type.value,
        "age": agent.age,
        "life_stage": agent.life_stage.value,
        "health": agent.health,
        "needs": {
            "hunger": agent.needs.hunger,
            "thirst": agent.needs.thirst,
            "energy": agent.needs.energy,
            "safety": agent.needs.safety,
            "social": agent.needs.social,
        },
        "inventory": {
            "food": agent.inventory.food,
            "wood": agent.inventory.wood,
            "stone": agent.inventory.stone,
        },
        "heading": agent.heading,
        "tribe_id": agent.tribe_id,
        "role": agent.role.value,
        "state": agent.state.value,
        "thought": agent.thought,
        "goal": agent.goal,
        "alive": agent.alive,
        "death_cause": None if agent.death_cause is None else agent.death_cause.value,
        "born_tick": agent.born_tick,
    }


def _relationship_to_dict(relationship: Relationship) -> dict[str, Any]:
    return {
        "trust": relationship.trust,
        "reputation": relationship.reputation,
        "moves": list(relationship.moves),
        "own_moves": list(relationship.own_moves),
        "payoffs": list(relationship.payoffs),
        "interactions": relationship.interactions,
        "last_tick": relationship.last_tick,
        "is_ally": relationship.is_ally,
        "caught_lying": relationship.caught_lying,
        "betrayals": relationship.betrayals,
    }


def _memory_to_dict(memory: AgentMemory) -> dict[str, Any]:
    return {
        "episodic": [
            {
                "tick": event.tick,
                "sim_seconds": event.sim_seconds,
                "type": event.type.value,
                "summary": event.summary,
                "actors": list(event.actors),
                "importance": event.importance,
            }
            for event in memory.episodic
        ],
        "social": {
            str(other_id): _relationship_to_dict(relationship)
            for other_id, relationship in sorted(memory.social.items())
        },
        "beliefs": list(memory.beliefs),
        "important_remembered": memory.important_remembered,
    }


def dump_world(world: World, minds: MindRegistry, ledger: SocialLedger) -> dict[str, Any]:
    """Serialise everything a world needs to be resumed."""
    return {
        "format": FORMAT_VERSION,
        "config": world.config.model_dump(mode="json"),
        "clock": {
            "tick": world.clock.tick,
            "season_offset": world.clock.season_offset,
        },
        "counters": {
            "next_agent_id": world.next_agent_id,
            "next_resource_id": world.next_resource_id,
            "next_tribe_id": world.next_tribe_id,
            "next_shelter_id": world.next_shelter_id,
            "births": world.births,
            "deaths": world.deaths,
        },
        "agents": [_agent_to_dict(agent) for _, agent in sorted(world.agents.items())],
        "resources": [
            {
                "id": node.id,
                "kind": node.kind.value,
                "position": list(node.position),
                "amount": node.amount,
                "capacity": node.capacity,
                "regrowth_per_sim_s": node.regrowth_per_sim_s,
                "infinite": node.infinite,
            }
            for _, node in sorted(world.resources.items())
        ],
        "tribes": [
            {
                "id": tribe.id,
                "name": tribe.name,
                "colour": tribe.colour,
                "leader_id": tribe.leader_id,
                "member_ids": sorted(tribe.member_ids),
                "storage_food": tribe.storage_food,
                "camp_position": list(tribe.camp_position),
                "territory_radius": tribe.territory_radius,
                "founded_tick": tribe.founded_tick,
                "at_war_with": sorted(tribe.at_war_with),
                "allied_with": sorted(tribe.allied_with),
            }
            for _, tribe in sorted(world.tribes.items())
        ],
        "shelters": [
            {
                "id": shelter.id,
                "position": list(shelter.position),
                "owner_id": shelter.owner_id,
                "tribe_id": shelter.tribe_id,
                "quality": shelter.quality,
                "built_tick": shelter.built_tick,
            }
            for _, shelter in sorted(world.shelters.items())
        ],
        "minds": {
            str(agent_id): _memory_to_dict(mind.memory) for agent_id, mind in sorted(minds.items())
        },
        "ledger": ledger.to_dict(),
    }


# --------------------------------------------------------------------- load


def _agent_from_dict(raw: dict[str, Any]) -> Agent:
    position = tuple(raw["position"])
    agent = Agent(
        id=int(raw["id"]),
        name=str(raw["name"]),
        position=(float(position[0]), float(position[1])),
        traits=Traits(**raw["traits"]),
        strategy=raw["strategy"],
        brain_type=BrainType(raw["brain_type"]),
        age=float(raw["age"]),
        life_stage=LifeStage(raw["life_stage"]),
        health=float(raw["health"]),
        needs=Needs(**raw["needs"]),
        inventory=Inventory(**raw["inventory"]),
        heading=float(raw["heading"]),
        tribe_id=raw["tribe_id"],
        role=TribeRole(raw["role"]),
        state=AgentState(raw["state"]),
        thought=str(raw.get("thought", "")),
        goal=str(raw.get("goal", "")),
        alive=bool(raw["alive"]),
        born_tick=int(raw.get("born_tick", 0)),
    )
    cause = raw.get("death_cause")
    if cause is not None:
        agent.death_cause = DeathCause(cause)
    return agent


def _memory_from_dict(raw: dict[str, Any]) -> AgentMemory:
    memory = AgentMemory()
    for event in raw.get("episodic", []):
        memory.episodic.append(
            MemoryEvent(
                tick=int(event["tick"]),
                sim_seconds=float(event["sim_seconds"]),
                type=EventType(event["type"]),
                summary=str(event["summary"]),
                actors=tuple(event.get("actors", ())),
                importance=int(event.get("importance", 3)),
            )
        )
    for other_id, entry in raw.get("social", {}).items():
        relationship = memory.relationship(int(other_id))
        relationship.trust = float(entry["trust"])
        relationship.reputation = float(entry["reputation"])
        relationship.moves.extend(entry.get("moves", []))
        relationship.own_moves.extend(entry.get("own_moves", []))
        relationship.payoffs.extend(entry.get("payoffs", []))
        relationship.interactions = int(entry.get("interactions", 0))
        relationship.last_tick = int(entry.get("last_tick", 0))
        relationship.is_ally = bool(entry.get("is_ally", False))
        relationship.caught_lying = int(entry.get("caught_lying", 0))
        relationship.betrayals = int(entry.get("betrayals", 0))
    memory.beliefs = list(raw.get("beliefs", []))
    memory.important_remembered = int(raw.get("important_remembered", 0))
    return memory


def load_world(
    payload: dict[str, Any],
    builder: WorldBuilder,
    minds: MindRegistry,
    ledger: SocialLedger,
) -> World:
    """Rebuild a world from `dump_world` output.

    The terrain comes from the builder (config + seed), then every mutable
    thing is overwritten from the blob. Raises `ValueError` on a payload from
    an incompatible format version, rather than loading half a world.
    """
    version = int(payload.get("format", 0))
    if version != FORMAT_VERSION:
        msg = f"snapshot format {version} cannot be read (this build reads {FORMAT_VERSION})"
        raise ValueError(msg)

    config = WorldConfig.model_validate(payload["config"])
    world = builder.build(config)

    world.agents.clear()
    world.resources.clear()
    world.tribes.clear()
    world.shelters.clear()

    clock = payload["clock"]
    # `sim_seconds` is derived from the tick, so storing it would be storing
    # the same fact twice - and the two could then disagree.
    world.clock = SimClock(
        tick=int(clock["tick"]),
        dt=config.dt,
        day_seconds=config.day_seconds,
        days_per_season=config.days_per_season,
        season_offset=int(clock["season_offset"]),
    )

    for raw in payload["agents"]:
        agent = _agent_from_dict(raw)
        world.agents[agent.id] = agent

    for raw in payload["resources"]:
        node = ResourceNode(
            id=int(raw["id"]),
            kind=ResourceKind(raw["kind"]),
            position=(float(raw["position"][0]), float(raw["position"][1])),
            amount=float(raw["amount"]),
            capacity=float(raw["capacity"]),
            regrowth_per_sim_s=float(raw["regrowth_per_sim_s"]),
            infinite=bool(raw["infinite"]),
        )
        world.resources[node.id] = node

    for raw in payload["tribes"]:
        tribe = Tribe(
            id=int(raw["id"]),
            name=str(raw["name"]),
            colour=str(raw["colour"]),
            leader_id=raw["leader_id"],
            member_ids=set(raw["member_ids"]),
            storage_food=float(raw["storage_food"]),
            camp_position=(float(raw["camp_position"][0]), float(raw["camp_position"][1])),
            territory_radius=float(raw["territory_radius"]),
            founded_tick=int(raw["founded_tick"]),
            at_war_with=set(raw["at_war_with"]),
            allied_with=set(raw["allied_with"]),
        )
        world.tribes[tribe.id] = tribe

    for raw in payload["shelters"]:
        shelter = Shelter(
            id=int(raw["id"]),
            position=(float(raw["position"][0]), float(raw["position"][1])),
            owner_id=int(raw["owner_id"]),
            tribe_id=raw["tribe_id"],
            quality=float(raw["quality"]),
            built_tick=int(raw["built_tick"]),
        )
        world.shelters[shelter.id] = shelter

    counters = payload["counters"]
    world.next_agent_id = int(counters["next_agent_id"])
    world.next_resource_id = int(counters["next_resource_id"])
    world.next_tribe_id = int(counters["next_tribe_id"])
    world.next_shelter_id = int(counters["next_shelter_id"])
    world.births = int(counters["births"])
    world.deaths = int(counters["deaths"])

    # Both indices are derived state; rebuilding is cheaper and safer than
    # storing them, and it cannot disagree with the positions above.
    world.agent_index.rebuild(
        (agent.id, agent.position[0], agent.position[1]) for agent in world.living_agents()
    )
    world.resource_index.rebuild(
        (node.id, node.position[0], node.position[1]) for node in world.resources.values()
    )
    world.invalidate_living()

    # Drops every mind from the world being replaced, so one world's
    # memories can never survive into another.
    minds.on_world_replaced(world)
    for agent_id, raw in payload.get("minds", {}).items():
        minds.require(int(agent_id)).memory = _memory_from_dict(raw)

    ledger.clear()
    ledger.load(payload.get("ledger", {}))
    return world
