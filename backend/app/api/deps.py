"""FastAPI dependencies: typed access to the container on `app.state`."""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.container import Container
from app.core.settings import Settings
from app.services.metrics_service import MetricsService
from app.services.run_archive import RunArchive
from app.services.simulation_service import SimulationService
from app.services.snapshot_service import SnapshotService


def get_container(request: Request) -> Container:
    """Return the container built by the app factory."""
    return cast("Container", request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    """Return application settings."""
    return container.settings


def get_simulation(container: ContainerDep) -> SimulationService:
    """Return the simulation service."""
    return container.simulation


def get_metrics(container: ContainerDep) -> MetricsService:
    """Return the metrics service."""
    return container.metrics


def get_archive(container: ContainerDep) -> RunArchive:
    """Return the durable record of the current run."""
    return container.archive


def get_snapshots(container: ContainerDep) -> SnapshotService:
    """Return the snapshot service."""
    return container.snapshots


SettingsDep = Annotated[Settings, Depends(get_settings)]
SimulationDep = Annotated[SimulationService, Depends(get_simulation)]
MetricsDep = Annotated[MetricsService, Depends(get_metrics)]
ArchiveDep = Annotated[RunArchive, Depends(get_archive)]
SnapshotsDep = Annotated[SnapshotService, Depends(get_snapshots)]
