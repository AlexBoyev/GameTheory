"""Typed application settings (environment + `.env`, see docs/SPEC.md section 12)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProviderName = Literal["mock", "ollama"]
"""Only local providers exist by design - no cloud AI, no API keys (CLAUDE.md)."""

HighSpeedPolicy = Literal["off", "reduced", "full"]
"""What to do with LLM calls when the simulation runs faster than 5x."""

Environment = Literal["dev", "test", "prod"]


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables or `.env`.

    Field names map to upper-case environment variables (`sim_seed` <- `SIM_SEED`).
    Both `backend/.env` and the repo-root `.env` are read, the latter winning.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- app
    app_name: str = "Game Theory"
    env: Environment = "dev"
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    # --- simulation
    sim_seed: int = 1337
    sim_tick_rate: float = Field(default=10.0, gt=0, description="Ticks per second at 1x speed.")
    sim_dt: float = Field(default=0.1, gt=0, description="Sim-seconds advanced per tick.")
    sim_max_agents: int = Field(default=1000, gt=0)
    sim_broadcast_hz: float = Field(default=20.0, gt=0, le=60)
    sim_day_seconds: float = Field(default=240.0, gt=0, description="Sim-seconds per day.")
    sim_days_per_season: int = Field(default=7, gt=0)
    sim_softmax_temperature: float = Field(
        default=0.35,
        gt=0,
        le=2.0,
        description="Utility-AI choice randomness; higher means more personality.",
    )

    # --- llm (see SPEC section 7.5)
    llm_enabled: bool = True
    llm_provider: LlmProviderName = "mock"
    llm_max_agents: int = Field(default=8, ge=0)
    llm_max_concurrency: int = Field(default=1, ge=1)
    llm_max_calls_per_min: int = Field(default=30, ge=1)
    llm_min_interval_sim_s: float = Field(default=20.0, ge=0)
    llm_timeout_s: float = Field(default=20.0, gt=0)
    llm_circuit_failures: int = Field(default=3, ge=1)
    llm_circuit_cooldown_s: float = Field(default=60.0, gt=0)
    llm_high_speed_policy: HighSpeedPolicy = "reduced"
    llm_cache_size: int = Field(default=256, ge=0)

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"

    # --- paths
    data_dir: Path = Path("../data")
    config_dir: Path = Path("config")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """SQLite URL inside `data_dir` (see SPEC section 11)."""
        return f"sqlite:///{(self.data_dir / 'gametheory.db').as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
