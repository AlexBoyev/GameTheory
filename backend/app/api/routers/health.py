"""Liveness, including whether a local model is actually reachable."""

from fastapi import APIRouter

from app import __version__
from app.api.deps import SettingsDep, SimulationDep
from app.api.dto.common import HealthDTO, LLMHealthDTO

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthDTO, summary="Liveness and LLM status")
def health(settings: SettingsDep, simulation: SimulationDep) -> HealthDTO:
    """Return process health plus the LLM gateway's view of the world."""
    status = simulation.llm_status()
    return HealthDTO(
        status="ok",
        app=settings.app_name,
        version=__version__,
        env=settings.env,
        llm=LLMHealthDTO(
            enabled=status.enabled,
            provider=status.provider,
            model=status.model,
            reachable=status.reachable,
            circuit_open=status.circuit_open,
            fallback_active=status.fallback_active,
        ),
    )
