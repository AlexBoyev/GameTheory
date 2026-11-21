"""Advancing whatever each agent is currently doing."""

from app.ai.minds import MindRegistry
from app.ai.skills.base import SkillStatus
from app.ai.skills.helpers import stop
from app.ai.skills.registry import SkillRegistry
from app.sim.entities import AgentState
from app.sim.world import World


class SkillExecutionSystem:
    """Steps each running skill and clears it when it finishes."""

    name = "skills"

    __slots__ = ("_minds", "_registry")

    def __init__(self, minds: MindRegistry, registry: SkillRegistry) -> None:
        self._minds = minds
        self._registry = registry

    def step(self, world: World, dt: float) -> None:
        """Advance every active skill run by `dt`."""
        now = world.clock.sim_seconds

        for agent in world.living_agents():
            mind = self._minds.get(agent.id)
            if mind is None or mind.run is None:
                continue

            skill = self._registry.get(mind.run.skill)
            if skill is None:
                self._clear(world, agent.id, mind_cleared=True)
                continue

            status = skill.step(mind.run, world, dt)
            if status is SkillStatus.RUNNING:
                continue

            definition = type(skill)
            mind.start_cooldown(definition.name, now, definition.cooldown)
            self._clear(world, agent.id, mind_cleared=True)

    def _clear(self, world: World, agent_id: int, *, mind_cleared: bool) -> None:
        """Drop the finished run and return the agent to idle."""
        agent = world.agents.get(agent_id)
        mind = self._minds.get(agent_id)
        if mind is not None and mind_cleared:
            mind.run = None
        if agent is None:
            return
        agent.current_skill = None
        if agent.alive:
            agent.state = AgentState.IDLE
            stop(agent)
