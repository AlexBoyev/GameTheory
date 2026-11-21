"""Headless throughput benchmark.

    uv run python -m app.tools.bench --agents 500 --ticks 2000

Runs the real tick pipeline - perception, needs, decisions, skills, movement,
regrowth, lifecycle - with no server, no sockets and no pacing, so the number
it prints is the engine's ceiling on this machine (SPEC section 7.6).
"""

import argparse
import time
from dataclasses import dataclass

from app.ai.minds import MindRegistry
from app.ai.skills.registry import build_registry
from app.core.world_config import TerrainConfig, WorldConfig
from app.services.engine_factory import build_pipeline
from app.sim.worldgen import IslandWorldBuilder


@dataclass(frozen=True, slots=True)
class BenchResult:
    """One benchmark run."""

    agents: int
    ticks: int
    seconds: float
    survivors: int
    build_seconds: float

    @property
    def ticks_per_second(self) -> float:
        """Throughput."""
        return self.ticks / self.seconds if self.seconds > 0 else float("inf")

    @property
    def realtime_multiple(self) -> float:
        """How many times faster than 1x (10 ticks/s) this is."""
        return self.ticks_per_second / 10.0

    def format_line(self) -> str:
        """Return a one-line summary."""
        return (
            f"agents={self.agents:>5}  ticks={self.ticks:>6}  "
            f"build={self.build_seconds:5.2f}s  run={self.seconds:7.2f}s  "
            f"{self.ticks_per_second:9.1f} ticks/s  "
            f"{self.realtime_multiple:7.1f}x realtime  "
            f"survivors={self.survivors}"
        )


def run_bench(agents: int, ticks: int, seed: int = 1337) -> BenchResult:
    """Build a world of `agents` and run `ticks` ticks as fast as possible."""
    config = WorldConfig(
        seed=seed,
        population=agents,
        max_agents=max(agents, 1),
        terrain=TerrainConfig(),
    )

    build_started = time.perf_counter()
    world = IslandWorldBuilder().build(config)
    build_seconds = time.perf_counter() - build_started

    skills = build_registry()
    minds = MindRegistry()
    pipeline = build_pipeline(minds, skills, temperature=0.35)
    pipeline.on_world_replaced(world)

    started = time.perf_counter()
    for _ in range(ticks):
        pipeline.step(world, world.clock.dt)
        world.clock = world.clock.advance()
        world.events.drain()
    elapsed = time.perf_counter() - started

    return BenchResult(
        agents=agents,
        ticks=ticks,
        seconds=elapsed,
        survivors=world.population,
        build_seconds=build_seconds,
    )


def main() -> None:
    """Parse arguments and print one result line per population."""
    parser = argparse.ArgumentParser(description="Game Theory throughput benchmark")
    parser.add_argument(
        "--agents",
        type=int,
        nargs="+",
        default=[100, 500, 1000],
        help="One or more population sizes to benchmark.",
    )
    parser.add_argument("--ticks", type=int, default=1000, help="Ticks per run.")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    print(f"Game Theory bench - {args.ticks} ticks, seed {args.seed}")
    print(f"skills registered: {len(build_registry())}")
    for agents in args.agents:
        print(run_bench(agents, args.ticks, args.seed).format_line())


if __name__ == "__main__":
    main()
