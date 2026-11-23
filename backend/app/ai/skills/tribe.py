"""What every tribe skill shares: the dials, and who a tribe would follow.

The skills themselves live next door, split by what they are *about* rather
than by type, because that is how they are read: joining and leaving one file,
the common store another, taking power and making war a third.

Importing this module also imports those, so `SkillRegistry.discover` finds
every tribe skill wherever it looks.
"""

from app.ai.minds import MindRegistry
from app.sim.entities import Agent, Tribe
from app.sim.world import World

FOUND_CHARISMA = 0.55
FOUND_ALLIES = 1
JOIN_TRUST = 0.3
STORE_AMOUNT = 2.0
TAKE_AMOUNT = 2.0
COUP_MARGIN = 0.05
"""How far a challenger must out-rank the leader in `legitimacy` to win.

Measured, not guessed: sampling every tribe every 200 ticks over a 12,000
tick run, the best-placed rival beat the sitting leader by at most +0.208,
and the median gap was -0.047. The old 0.25 therefore sat outside the entire
observed distribution - 35 coups were attempted and none could ever have
succeeded. At 0.05 a rival the tribe genuinely prefers can win, and roughly
one attempt in ten does.
"""


def legitimacy(world: World, agent: Agent, tribe: Tribe, minds: MindRegistry) -> float:
    """Reputation x charisma x tenure - who the tribe would follow (SPEC 6).

    "Reputation" here is literally what the members think: the average trust
    the tribe holds in this agent. A leader nobody likes is not legitimate,
    however charismatic.

    Tenure is the *tribe's* age, not this agent's, so it is the same for the
    incumbent and the challenger: it widens the gap between them as a tribe
    settles rather than protecting whoever holds the post. Compare two
    members of one tribe with it; do not compare across tribes.
    """
    standing = 0.0
    counted = 0
    for member_id in sorted(tribe.member_ids):
        if member_id == agent.id or member_id not in world.agents:
            continue
        relationship = minds.require(member_id).memory.social.get(agent.id)
        if relationship is not None:
            standing += relationship.trust
            counted += 1
    average = standing / counted if counted else 0.0
    tenure = min(1.0, (world.clock.tick - tribe.founded_tick) / 6000.0)
    return (0.5 + 0.5 * average) * (0.4 + 0.6 * agent.traits.charisma) * (0.7 + 0.3 * tenure)


def _register_subject_modules() -> None:
    """Import the skill modules so `SkillRegistry.discover` sees them.

    Called at import time. The import is inside a function rather than at the
    top of the file because those modules import the constants above, and a
    top-level import either way round is a cycle.
    """
    from app.ai.skills import (  # noqa: F401
        tribe_diplomacy,
        tribe_membership,
        tribe_politics,
        tribe_storage,
    )


_register_subject_modules()
