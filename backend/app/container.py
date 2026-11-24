"""The composition root.

Everything is constructor-injected and assembled exactly once, here. No module
anywhere else reaches for a global service (CLAUDE.md architecture rule 4).
"""

import asyncio
from dataclasses import dataclass

from app.ai.llm.gateway import LLMGateway
from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.ollama_provider import OllamaProvider
from app.ai.llm.provider import LLMProvider
from app.ai.skills.registry import SkillRegistry
from app.core.logging import get_logger
from app.core.settings import Settings
from app.core.world_config import WorldConfig
from app.persistence.database import build_engine
from app.persistence.repository import Repository
from app.services.llm_pump import LLMPump
from app.services.metrics_service import MetricsService
from app.services.run_archive import RunArchive
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
    archive: RunArchive
    gateway: LLMGateway
    skills: SkillRegistry
    simulation: SimulationService
    metrics: MetricsService
    snapshots: SnapshotService
    llm_pump: LLMPump

    async def startup(self) -> None:
        """Create tables, probe the LLM provider and bring the world up paused."""
        self.repository.initialise()
        # Before the simulation starts: the first thing it does is open a run.
        self.archive.start()
        skill_count = len(self.skills)
        reachable = await self.gateway.check_health()
        if not reachable:
            LOG.warning(
                "llm.unreachable",
                provider=self.gateway.status().provider,
                detail="falling back to deterministic mock plans",
            )
        # Ready, not running: nothing ticks until someone presses Start.
        await self.simulation.boot()
        self.llm_pump.start()
        LOG.info("container.started", skills=skill_count, llm_reachable=reachable)

    async def shutdown(self) -> None:
        """Stop the pump and the broadcast loop, then release the transport."""
        await self.llm_pump.stop()
        await self.simulation.shutdown()
        # After the simulation, so the closing `end` is already queued.
        await asyncio.to_thread(self.archive.stop)
        await self.gateway.aclose()


def build_container(settings: Settings, config: WorldConfig | None = None) -> Container:
    """Construct every service for `settings`.

    `config` overrides the world the simulation starts with; tests use it to
    build a small island instead of waiting for a full one.
    """
    repository = Repository(build_engine(settings))
    archive = RunArchive(repository)
    gateway = LLMGateway(settings, build_provider(settings))
    metrics = MetricsService(settings, archive)
    simulation = SimulationService(
        settings, gateway, config=config, metrics=metrics, archive=archive
    )
    return Container(
        settings=settings,
        repository=repository,
        archive=archive,
        gateway=gateway,
        # The simulation owns the registry its skills are bound to; exposing
        # that one rather than a second, unbound registry.
        skills=simulation.skills,
        simulation=simulation,
        metrics=metrics,
        snapshots=SnapshotService(repository),
        llm_pump=LLMPump(simulation.broker, gateway),
    )
