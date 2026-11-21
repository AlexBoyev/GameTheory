"""Tuning constants for the survival loop.

Immutable module-level values: these are the dials that decide whether a world
is a garden or a graveyard, and they are gathered in one file so balancing is a
single diff rather than a hunt through the systems.

Rates are per sim-second unless the name says otherwise. One sim-day is 240
sim-seconds by default, so "0.5 per sim-second" empties a need in ~0.8 days.
"""

from typing import Final

# ------------------------------------------------------------------ needs
HUNGER_DECAY: Final = 0.35
THIRST_DECAY: Final = 0.5
ENERGY_DECAY: Final = 0.25
ENERGY_DECAY_NIGHT: Final = 0.4
SOCIAL_DECAY: Final = 0.1
SAFETY_RECOVERY: Final = 3.5
"""Safety drifts back up when nothing threatening is nearby.

Must be the same order as `PerceptionSystem.THREAT_FEAR_RATE`, or fear becomes
permanent rather than a passing fright: at 0.6 against a drain of 14, a
crowded island pinned every agent's safety at zero, and they fled instead of
drinking until they died of thirst.
"""

NEED_MAX: Final = 100.0
NEED_URGENT: Final = 30.0
"""Below this a need starts dominating the utility scores."""

# ------------------------------------------------------------------ health
STARVATION_DAMAGE: Final = 1.5
DEHYDRATION_DAMAGE: Final = 2.0
EXHAUSTION_DAMAGE: Final = 0.3
HEALTH_REGEN: Final = 0.25
"""Health recovers slowly while every need is comfortable."""
HEALTH_REGEN_THRESHOLD: Final = 55.0

# ------------------------------------------------------------------ actions
WALK_SPEED: Final = 3.2
CHILD_SPEED_FACTOR: Final = 0.7
ELDER_SPEED_FACTOR: Final = 0.75
ARRIVAL_DISTANCE: Final = 0.9

EAT_PER_FOOD: Final = 40.0
"""Hunger restored by one unit of food."""
EAT_DURATION: Final = 1.5
DRINK_RATE: Final = 55.0
SLEEP_RATE: Final = 14.0
GATHER_RATE: Final = 2.5
"""Food (or wood) harvested per sim-second."""
CARRY_TARGET: Final = 5.0
"""Agents stop gathering once they hold this much food."""

RABBIT_FOOD: Final = 3.0
DEER_FOOD: Final = 14.0
HUNT_CATCH_BASE: Final = 0.35
"""Base chance per attempt to catch a rabbit, modified by courage and energy."""
HUNT_ATTEMPT_INTERVAL: Final = 1.0
FLEE_DURATION: Final = 4.0
WANDER_MIN_DURATION: Final = 2.0
WANDER_MAX_DURATION: Final = 6.0

# ------------------------------------------------------------------ resources
BERRY_CAPACITY: Final = 14.0
BERRY_REGROWTH: Final = 0.035
TREE_CAPACITY: Final = 20.0
TREE_REGROWTH: Final = 0.004
RABBIT_CAPACITY: Final = 1.0
RABBIT_REGROWTH: Final = 0.01
DEER_CAPACITY: Final = 1.0
DEER_REGROWTH: Final = 0.003
WINTER_REGROWTH_FACTOR: Final = 0.0
"""Winter stops berry regrowth entirely (SPEC 3.2)."""

RESOURCE_DENSITY: Final = 0.0045
"""Resource nodes per square world unit of land, before scarcity scaling.

Sized from the food balance, not by eye. Each agent burns
`HUNGER_DECAY / EAT_PER_FOOD` food per sim-second (0.009), so the default 120
agents need about 1.05 food/sim-s. At this density a 256-unit island carries
roughly 47 bushes (`BERRY_REGROWTH` each) plus 17 rabbits, which is a little
over 2 food/sim-s - comfortable in summer, and genuinely frightening in winter
when `WINTER_REGROWTH_FACTOR` stops berry regrowth entirely.

At the previous 0.0018 the island could only feed about 68 agents, so the
default world starved itself down to 14 survivors by tick 9000.
"""

# ------------------------------------------------------------------ lifecycle
AGE_YEARS_PER_DAY: Final = 1.0
"""Ages fast on purpose: a lifetime should be watchable in minutes."""
CHILD_UNTIL: Final = 16.0
ELDER_FROM: Final = 55.0
MAX_AGE: Final = 72.0
OLD_AGE_DAMAGE: Final = 0.8
"""Health loss per sim-second once past `MAX_AGE`."""
CORPSE_FOOD: Final = 2.0
CORPSE_DECAY_S: Final = 60.0

# ------------------------------------------------------------------ perception
VISION_RADIUS: Final = 18.0

LANDMARK_RADIUS: Final = 54.0
"""How far an agent knows its own territory, for permanent features only.

Vision is 18 units, which is the right model for a rabbit or a rival: they
move, so you only know about them when you can see them. A lake does not
move. An animal that has lived here knows roughly where the water is, and
modelling it as invisible beyond 18 units killed inland agents of thirst
beside a lake they would obviously have known about.

Applies to water only. Food still has to be found, which is what makes
foraging - and later, telling someone where the berries are - meaningful.
"""
THREAT_AGGRESSION: Final = 0.8
"""Neighbours above this aggression make an agent feel unsafe.

High on purpose: merely sharing a meadow with a bad-tempered neighbour is not
an emergency. Real violence arrives with combat in Phase 4.
"""
THREAT_RADIUS: Final = 5.0
"""Close enough to be menacing - roughly an arm's length in world units."""
