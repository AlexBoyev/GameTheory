"""Read-only views of the running world for the REST API.

Payloads are plain dicts shaped exactly like the DTOs in `api/dto`, which
validate them on the way out. That avoids a third set of mirror classes
between the world and the wire.

Every method holds the engine lock only for as long as it takes to copy what
it needs - the tick loop is waiting on it.
"""

import base64
from typing import Any

from app.ai.minds import MindRegistry
from app.sim.engine import SimulationEngine
from app.sim.entities import Agent
from app.sim.worldgen.terrain import biome_names

DEFAULT_AGENT_LIMIT = 500


class WorldQueries:
    """Answers "what does the world look like right now?" for `api/`."""

    __slots__ = ("_engine", "_minds")

    def __init__(self, engine: SimulationEngine, minds: MindRegistry) -> None:
        self._engine = engine
        self._minds = minds

    # ---------------------------------------------------------------- terrain

    def terrain_payload(self) -> dict[str, Any]:
        """Return the heightmap and biome map as base64 arrays."""
        with self._engine.read_world() as world:
            terrain = world.terrain
            heights = terrain.heights.astype("<f4", copy=False).tobytes()
            biomes = terrain.biomes.astype("<u1", copy=False).tobytes()
            config = world.config.terrain
            resolution = terrain.resolution
            size = terrain.size
            water_level = terrain.water_level

        return {
            "size": size,
            "resolution": resolution,
            "water_level": water_level,
            "max_height": config.max_height,
            "heights_b64": base64.b64encode(heights).decode("ascii"),
            "biomes_b64": base64.b64encode(biomes).decode("ascii"),
            "biome_names": biome_names(),
        }

    # ----------------------------------------------------------------- agents

    def agent_summaries(self, limit: int = DEFAULT_AGENT_LIMIT) -> list[dict[str, Any]]:
        """Return one summary row per living agent, in id order."""
        with self._engine.read_world() as world:
            agents = world.living_agents()[:limit]
            return [self._summary(agent) for agent in agents]

    def agent_detail(self, agent_id: int) -> dict[str, Any] | None:
        """Return everything the inspector shows, or `None` if unknown."""
        with self._engine.read_world() as world:
            agent = world.agents.get(agent_id)
            if agent is None:
                return None
            names = {other.id: other.name for other in world.living_agents()}
            now_sim_s = world.clock.sim_seconds
            current_skill = agent.current_skill
            payload = {
                "summary": self._summary(agent),
                "age": round(agent.age, 2),
                "life_stage": agent.life_stage.value,
                "needs": {
                    "hunger": round(agent.needs.hunger, 2),
                    "thirst": round(agent.needs.thirst, 2),
                    "energy": round(agent.needs.energy, 2),
                    "safety": round(agent.needs.safety, 2),
                    "social": round(agent.needs.social, 2),
                },
                "traits": {
                    "aggression": round(agent.traits.aggression, 3),
                    "honesty": round(agent.traits.honesty, 3),
                    "loyalty": round(agent.traits.loyalty, 3),
                    "greed": round(agent.traits.greed, 3),
                    "sociability": round(agent.traits.sociability, 3),
                    "cunning": round(agent.traits.cunning, 3),
                    "courage": round(agent.traits.courage, 3),
                    "charisma": round(agent.traits.charisma, 3),
                },
                "inventory": {
                    "food": round(agent.inventory.food, 2),
                    "wood": round(agent.inventory.wood, 2),
                    "stone": round(agent.inventory.stone, 2),
                },
                "current_skill": agent.current_skill,
                "intent": agent.intent,
                "thought": agent.thought,
            }

        mind = self._minds.get(agent_id)
        payload["decision_trace"] = (
            [
                {
                    "skill": option.skill,
                    "score": option.score,
                    "reason": option.reason,
                    "chosen": option.skill == current_skill,
                }
                for option in mind.trace
            ]
            if mind is not None
            else []
        )
        payload["relationships"] = (
            [
                {
                    "other_id": other_id,
                    "other_name": names.get(other_id, f"#{other_id}"),
                    "trust": round(relationship.trust, 3),
                    "reputation": round(relationship.reputation, 3),
                    "interactions": relationship.interactions,
                    "is_ally": relationship.is_ally,
                    "caught_lying": relationship.caught_lying,
                }
                for other_id, relationship in mind.memory.top_relationships()
            ]
            if mind is not None
            else []
        )
        payload["memories"] = (
            [
                {
                    "tick": event.tick,
                    "type": event.type.value,
                    "summary": event.summary,
                    "importance": event.importance,
                }
                for event in mind.memory.recall(now_sim_s)
            ]
            if mind is not None
            else []
        )
        payload["llm"] = None
        return payload

    @staticmethod
    def _summary(agent: Agent) -> dict[str, Any]:
        """Return the compact row shared by the list and detail endpoints."""
        return {
            "id": agent.id,
            "name": agent.name,
            "x": round(agent.position[0], 2),
            "z": round(agent.position[1], 2),
            "state": agent.state.value,
            "strategy": agent.strategy,
            "brain_type": agent.brain_type.value,
            "tribe_id": agent.tribe_id,
            "role": agent.role.value,
            "health": round(agent.health, 1),
            "alive": agent.alive,
        }
