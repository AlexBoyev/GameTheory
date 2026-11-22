"""What every manipulation skill shares: the dials.

The skills themselves are split by what they do to somebody: `deception`
spreads false information, `coercion` works on a person directly. Importing
this module imports both, so skill discovery finds them wherever it looks.
"""

GOSSIP_DURATION = 2.0
BRIBE_AMOUNT = 1.5
KNOWS_BETTER_TRUST = 0.35
"""Trust in the subject above which the listener has evidence of their own."""


def _register_subject_modules() -> None:
    """Import the skill modules so `SkillRegistry.discover` sees them.

    Inside a function because those modules import the constants above, and a
    top-level import either way round is a cycle.
    """
    from app.ai.skills import coercion, deception  # noqa: F401


_register_subject_modules()
