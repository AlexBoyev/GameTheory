"""Simulation entities: agents, resource nodes, tribes (SPEC sections 3.1, 4, 6)."""

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.world_config import StrategyName
from app.sim.balance import CHILD_UNTIL, ELDER_FROM


class LifeStage(StrEnum):
    """Coarse age bracket; drives size, fertility and work capability."""

    CHILD = "child"
    ADULT = "adult"
    ELDER = "elder"


def life_stage_for(age: float) -> "LifeStage":
    """Return the life stage for `age` in years (thresholds in `balance`)."""
    if age < CHILD_UNTIL:
        return LifeStage.CHILD
    if age >= ELDER_FROM:
        return LifeStage.ELDER
    return LifeStage.ADULT


class DeathCause(StrEnum):
    """Why an agent died - aggregated in the metrics panel."""

    STARVATION = "starvation"
    DEHYDRATION = "dehydration"
    COMBAT = "combat"
    OLD_AGE = "old_age"
    PLAGUE = "plague"
    SMITE = "smite"


class BrainType(StrEnum):
    """Which decision stack an agent runs (SPEC section 7.1)."""

    UTILITY = "utility"
    LLM = "llm"


class TribeRole(StrEnum):
    """An agent's standing inside its tribe."""

    NONE = "none"
    MEMBER = "member"
    ELDER = "elder"
    LEADER = "leader"


class AgentState(StrEnum):
    """Visible activity, mapped to an emoji sprite by the frontend."""

    IDLE = "idle"
    WANDER = "wander"
    MOVE = "move"
    GATHER = "gather"
    EAT = "eat"
    DRINK = "drink"
    SLEEP = "sleep"
    HUNT = "hunt"
    FLEE = "flee"
    TALK = "talk"
    SCHEME = "scheme"
    FIGHT = "fight"
    TRADE = "trade"
    BUILD = "build"
    DEAD = "dead"


class ResourceKind(StrEnum):
    """Harvestable things in the world (SPEC section 3.1)."""

    BERRY_BUSH = "berry_bush"
    TREE = "tree"
    WATER = "water"
    RABBIT = "rabbit"
    DEER = "deer"
    STONE = "stone"
    CORPSE = "corpse"
    """A body leaves food behind briefly (SPEC section 4.2)."""


FOOD_KINDS: frozenset[ResourceKind] = frozenset(
    {ResourceKind.BERRY_BUSH, ResourceKind.RABBIT, ResourceKind.DEER, ResourceKind.CORPSE}
)
"""Resource kinds that can end up in an inventory as food."""


class Biome(StrEnum):
    """Terrain classification by height and moisture (SPEC section 3)."""

    WATER = "water"
    BEACH = "beach"
    MEADOW = "meadow"
    FOREST = "forest"
    HILLS = "hills"
    PEAKS = "peaks"


@dataclass(slots=True)
class Needs:
    """Drives, 0-100, decaying every tick. 0 is desperate, 100 is satisfied."""

    hunger: float = 100.0
    thirst: float = 100.0
    energy: float = 100.0
    safety: float = 100.0
    social: float = 100.0


@dataclass(frozen=True, slots=True)
class Traits:
    """Fixed personality, 0-1, inherited with blending and mutation."""

    aggression: float = 0.5
    honesty: float = 0.5
    loyalty: float = 0.5
    greed: float = 0.5
    sociability: float = 0.5
    cunning: float = 0.5
    courage: float = 0.5
    charisma: float = 0.5


@dataclass(slots=True)
class Inventory:
    """What an agent carries."""

    food: float = 0.0
    wood: float = 0.0
    stone: float = 0.0


@dataclass(slots=True)
class Agent:
    """One inhabitant of the island (field reference: SPEC section 4.1)."""

    id: int
    name: str
    position: tuple[float, float]
    traits: Traits
    strategy: StrategyName
    brain_type: BrainType = BrainType.UTILITY

    age: float = 18.0
    life_stage: LifeStage = LifeStage.ADULT
    health: float = 100.0
    needs: Needs = field(default_factory=Needs)
    inventory: Inventory = field(default_factory=Inventory)

    heading: float = 0.0
    velocity: tuple[float, float] = (0.0, 0.0)

    tribe_id: int | None = None
    role: TribeRole = TribeRole.NONE

    state: AgentState = AgentState.IDLE
    current_skill: str | None = None
    intent: str | None = None
    thought: str = ""

    alive: bool = True
    death_cause: DeathCause | None = None
    born_tick: int = 0

    @property
    def is_adult(self) -> bool:
        """True for adults and elders."""
        return self.life_stage is not LifeStage.CHILD


@dataclass(slots=True)
class ResourceNode:
    """A berry bush, tree, water tile or animal (SPEC section 3.1)."""

    id: int
    kind: ResourceKind
    position: tuple[float, float]
    amount: float
    capacity: float
    regrowth_per_sim_s: float = 0.0
    infinite: bool = False

    @property
    def depleted(self) -> bool:
        """True when nothing can be harvested right now."""
        return not self.infinite and self.amount <= 0.0


@dataclass(slots=True)
class Shelter:
    """A hut. Sleeping in one is safer and more restful than sleeping in a field.

    Attributes:
        id: Stable identifier.
        position: Where it stands.
        owner_id: Who built it.
        tribe_id: Which tribe's camp it belongs to, if any.
        quality: 0-1; better shelters rest you faster.
        built_tick: When it went up.
    """

    id: int
    position: tuple[float, float]
    owner_id: int
    tribe_id: int | None = None
    quality: float = 1.0
    built_tick: int = 0


@dataclass(slots=True)
class Tribe:
    """An emergent group with a leader, storage, camp and territory."""

    id: int
    name: str
    colour: str
    leader_id: int | None = None
    member_ids: set[int] = field(default_factory=set)
    storage_food: float = 0.0
    camp_position: tuple[float, float] = (0.0, 0.0)
    territory_radius: float = 0.0
    founded_tick: int = 0
    at_war_with: set[int] = field(default_factory=set)
    allied_with: set[int] = field(default_factory=set)

    @property
    def size(self) -> int:
        """Current member count."""
        return len(self.member_ids)
