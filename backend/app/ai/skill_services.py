"""What a skill needs beyond the world: other agents' minds, and the tally.

Social skills act *on other people* - gossip changes what the listener
believes, a gift changes what they think of you - so they need the mind
registry, which `sim/` knows nothing about. Rather than smuggle a global in,
the registry binds this bundle onto each skill instance after discovery.
"""

from dataclasses import dataclass

from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry


@dataclass(frozen=True, slots=True)
class SkillServices:
    """Collaborators handed to every skill at registration time."""

    minds: MindRegistry
    ledger: SocialLedger
