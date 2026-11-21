"""The composition root.

Everything is constructor-injected and assembled exactly once, here. No module
anywhere else reaches for a global service (CLAUDE.md architecture rule 4).
"""

from dataclasses import dataclass

from app.ai.llm.gateway import LLMGateway
from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.ollama_provider import OllamaProvider
from app.ai.llm.provider import LLMProvider
from app.ai.skills.registry import SkillRegistry, build_registry
from app.core.logging import get_logger
from app.core.settings import Settings
from app.core.world_config import WorldConfig
from app.persistence.database import build_engine
from app.persistence.repository import Repository
from app.services.metrics_service import MetricsService
from app.services.simulation_service import SimulationService
from app.services.snapshot_service import SnapshotService

LOG = get_logger(__name__)


def build_provider(settings: Settings) -> LLMProvider:
    """Return the configured provider.

    `mock` is the default and needs nothing installed. `ollama` is constructed
    eagerly but never contacted here - reachability is probed on startup, and
    an unreachable daemon degrades to mock rather than failing the app.
    """
    if settings.llm_provider == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_url,
            model=settings.ollama_model,
            timeout_s=settings.llm_timeout_s,
        )
    return MockProvider()


@dataclass(frozen=True, slots=True)
class Container:
    """Wired application services, held on `app.state.container`."""

    settings: Settings
    repository: Repository
    gateway: LLMGateway
    skills: SkillRegistry
    simulation: SimulationService
    metrics: MetricsService
    snapshots: SnapshotService

    async def startup(self) -> None:
        """Create tables, probe the LLM provider and start broadcasting."""
        self.repository.initialise()
        skill_count = len(self.skills)
        reachable = await self.gateway.check_health()
        if not reachable:
            LOG.warning(
                "llm.unreachable",
                provider=self.gateway.status().provider,
                detail="falling back to deterministic mock plans",
            )
        await self.simulation.start()
        LOG.info("container.started", skills=skill_count, llm_reachable=reachable)

    async def shutdown(self) -> None:
        """Stop the broadcast loop and release the LLM transport."""
        await self.simulation.shutdown()
        await self.gateway.aclose()


def build_container(settings: Settings, config: WorldConfig | None = None) -> Container:
    """Construct every service for `settings`.

    `config` overrides the world the simulation starts with; tests use it to
    build a small island instead of waiting for a full one.
    """
    repository = Repository(build_engine(settings))
    gateway = LLMGateway(settings, build_provider(settings))
    simulation = SimulationService(settings, gateway, config=config)
    return Container(
        settings=settings,
        repository=repository,
        gateway=gateway,
        skills=build_registry(),
        simulation=simulation,
        metrics=MetricsService(settings, repository),
        snapshots=SnapshotService(repository),
    )
