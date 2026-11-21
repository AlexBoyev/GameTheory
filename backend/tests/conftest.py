"""Shared fixtures: isolated settings, an app wired for tests, world builders."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.minds import MindRegistry
from app.ai.skills.registry import SkillRegistry, build_registry
from app.container import build_container
from app.core.settings import Settings
from app.core.world_config import TerrainConfig, WorldConfig
from app.main import create_app
from app.services.engine_factory import build_pipeline
from app.sim.systems import SystemPipeline
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder

SMALL_TERRAIN = TerrainConfig(resolution=48, size=160.0)
"""Small enough to generate in a fraction of a second, big enough to have biomes."""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings that ignore the developer's `.env` and write to a temp dir."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="test",
        log_level="WARNING",
        data_dir=tmp_path / "data",
        llm_provider="mock",
        sim_seed=42,
    )


@pytest.fixture
def api_config() -> WorldConfig:
    """The world the API tests run against: small, so each test starts fast."""
    return WorldConfig(seed=42, population=20, max_agents=32, terrain=SMALL_TERRAIN)


@pytest.fixture
def client(settings: Settings, api_config: WorldConfig) -> Iterator[TestClient]:
    """A client with the lifespan running, so the engine is live."""
    app = create_app(settings, build_container(settings, api_config))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def small_config() -> WorldConfig:
    """A world small enough for fast tests but complete in every respect."""
    return WorldConfig(seed=7, population=24, max_agents=64, terrain=SMALL_TERRAIN)


@pytest.fixture
def world(small_config: WorldConfig) -> World:
    """A freshly generated world."""
    return IslandWorldBuilder().build(small_config)


@pytest.fixture
def skills() -> SkillRegistry:
    """Every shipped skill, discovered."""
    return build_registry()


@pytest.fixture
def pipeline(skills: SkillRegistry) -> SystemPipeline:
    """The real tick pipeline with its own mind registry."""
    return build_pipeline(MindRegistry(), skills, temperature=0.35)


def run_ticks(pipeline: SystemPipeline, world: World, ticks: int) -> None:
    """Advance `world` by `ticks` with no engine thread and no pacing."""
    for _ in range(ticks):
        pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()
        world.events.drain()


def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Poll `predicate` until it holds or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
