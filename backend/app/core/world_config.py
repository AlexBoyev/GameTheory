"""`WorldConfig` - the knobs a new world is generated from (SPEC sections 8, 12).

Lives in `core/` on purpose: `sim/` consumes it and `api/` exposes it verbatim,
so neither layer has to duplicate the schema.
"""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

StrategyName = Literal[
    "AlwaysCooperate",
    "AlwaysDefect",
    "TitForTat",
    "GenerousTFT",
    "Grudger",
    "Pavlov",
    "Detective",
    "Random",
    "Opportunist",
    "LLM",
]
"""The strategy "gene" pool (SPEC section 5.2)."""

STRATEGY_NAMES: tuple[StrategyName, ...] = get_args(StrategyName)
"""The same names at runtime, for validating what a caller asked for.

Derived from the type rather than written out again, so the two can never
drift - a god tool that accepted a strategy the engine has never heard of
would spawn an agent that cannot play.
"""

Season = Literal["spring", "summer", "autumn", "winter"]


def default_strategy_mix() -> dict[StrategyName, float]:
    """Return the balanced starting gene pool used when none is given."""
    return {
        "TitForTat": 0.25,
        "AlwaysCooperate": 0.15,
        "AlwaysDefect": 0.15,
        "Grudger": 0.1,
        "GenerousTFT": 0.1,
        "Pavlov": 0.1,
        "Detective": 0.05,
        "Random": 0.05,
        "Opportunist": 0.05,
    }


class TerrainConfig(BaseModel):
    """Island generation parameters (SPEC section 3)."""

    model_config = ConfigDict(extra="forbid")

    size: float = Field(default=256.0, gt=0, description="World extent in world units.")
    resolution: int = Field(default=128, ge=16, le=512, description="Heightmap grid cells.")
    octaves: int = Field(default=5, ge=1, le=8)
    falloff: float = Field(default=2.2, gt=0, description="Radial island falloff exponent.")
    water_level: float = Field(default=0.32, ge=0.0, le=1.0)
    max_height: float = Field(default=18.0, gt=0)


class WorldConfig(BaseModel):
    """Everything the engine needs to build and run a world deterministically."""

    model_config = ConfigDict(extra="forbid")

    seed: int = 1337
    terrain: TerrainConfig = Field(default_factory=TerrainConfig)

    # Time model (SPEC 2.2). Part of the world, not the process, so a world
    # restored from a snapshot keeps the clock it was built with.
    dt: float = Field(default=0.1, gt=0, description="Sim-seconds advanced per tick.")
    day_seconds: float = Field(default=240.0, gt=0, description="Sim-seconds per day.")
    days_per_season: int = Field(default=7, gt=0)

    population: int = Field(default=120, ge=1, le=5000)
    max_agents: int = Field(default=1000, ge=1, le=5000)
    initial_tribes: int = Field(default=0, ge=0, le=16)

    scarcity: float = Field(default=1.0, gt=0, le=4.0, description="Scales all resource yields.")

    age_years_per_day: float = Field(
        default=3.0,
        gt=0,
        le=12.0,
        description="Years an agent ages per sim-day; sets how fast generations turn over.",
    )
    """How fast a life runs, which is really how fast evolution runs.

    Strategies are inherited and mutated, so selection only bites if agents
    die of something other than bad luck. The old value of 1.0 was annotated
    "a lifetime should be watchable in minutes" and did not deliver it: in
    27,000 measured ticks nobody died of old age at all, and the oldest
    agent the world spawns would have needed 52,800. Three years a day puts
    a full life inside a session someone would actually sit through, without
    touching the food economy or the payoff matrices.
    """
    season_start: Season = "spring"

    strategy_mix: dict[StrategyName, float] = Field(
        default_factory=default_strategy_mix,
        description="Relative weights, normalised at spawn time.",
    )
    trait_bias: dict[str, float] = Field(
        default_factory=dict,
        description="Per-trait mean in 0..1; omitted traits stay centred on 0.5.",
    )
    """Shifts the personality distribution a whole world at a time.

    This is what makes a preset a *place* rather than a different number of
    berries: Liars' Island is low honesty and high cunning, Tribal Wars is
    loyal and aggressive. Only the mean moves - the spread stays, so a liars'
    island still has the occasional honest agent.
    """

    mutation_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    trembling_hand: float = Field(default=0.02, ge=0.0, le=0.5, description="Action-flip noise.")

    llm_agents: int = Field(default=4, ge=0, le=64, description="Agents with brain_type=llm.")
    """How many agents deliberate as well as react.

    Four by default so the deliberative layer is visible (haloes, speech
    bubbles, thoughts in the inspector) without being asked for: the default
    provider is the in-process mock, so this costs nothing and needs nothing
    installed. Set it to 0 for a bit-for-bit reproducible run - a model's
    replies arrive on the event loop, whose timing no seed controls.
    """

    tournament_mode: bool = Field(default=False, description="Survival off, round-robin IPD.")

    @property
    def normalised_strategy_mix(self) -> dict[StrategyName, float]:
        """Return `strategy_mix` scaled to sum to 1.0 (empty mix -> all TitForTat)."""
        total = sum(self.strategy_mix.values())
        if total <= 0:
            return {"TitForTat": 1.0}
        return {name: weight / total for name, weight in self.strategy_mix.items()}
