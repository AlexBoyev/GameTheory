"""Does the world actually do the things it can do?

Every skill in the registry is registered, typed, unit-tested and reachable
on paper. Three of them still never happened: `Raid` was wanted on
temperament alone and never outscored picking berries, no challenger could
ever clear `COUP_MARGIN`, and no code anywhere could add to
`Tribe.allied_with`. Each had a passing unit test, because a unit test sets
the stage itself - it proves a path works, not that the world walks it.

So this file runs a world and asks what happened. It is slower than a unit
test and it is the only kind of test that could have caught any of those.

Two traps worth knowing before changing anything here:

- *Read the score, not the trace.* The decision trace keeps only an agent's
  top three options, so a skill can be scored on every tick of every agent's
  life and never appear in it. Scoring the skills directly is what tells
  `Raid` (wanted, never won) apart from `MoveTo` (never wanted).
- *Sample every tick.* Checking every 25th missed `OfferPeace` in a seed
  that demonstrably made peace: the war began and ended in between. Skills
  already seen are skipped, so the sweep costs almost nothing after the
  first few hundred ticks.
"""

import pytest

from app.ai.brains.base import DecisionContext
from app.ai.gametheory.ledger import SocialLedger
from app.ai.minds import MindRegistry
from app.ai.skill_services import SkillServices
from app.ai.skills.registry import SkillRegistry, build_registry
from app.ai.skills.tribe import COUP_MARGIN, legitimacy
from app.core.world_config import TerrainConfig, WorldConfig
from app.services.engine_factory import build_pipeline
from app.sim.entities import TribeRole
from app.sim.events import EventType
from app.sim.world import World
from app.sim.worldgen import IslandWorldBuilder

SEED = 42
TICKS = 6000
"""Chosen together, by measurement rather than taste.

The pair has to be one where the whole tribe machinery turns inside the
window: every skill wanted by somebody, a war declared *and* settled (which
is the only way `OfferPeace` is ever scored), pacts signed, a coup won, and
a challenger who gets far enough above their leader to win one. Four
thousand ticks is not enough - no seed produces both a war and a winnable
coup that early.

Re-measured on 2026-11-25, because it had to be: making gatherers walk to
the next bush instead of giving up moved every world off its old
trajectory, and seed 101 stopped producing a war inside the window. It did
not stop producing one at all - a 24,000-tick run of the default world has
31 wars and 31 truces - which is the distinction this file exists to make,
and is why the failure was a re-measurement and not a bug.

Today's sweep, same criteria: seeds 23, 42, 99 and 1337 all pass; 7, 11, 77
and 101 miss (7 on the coup margin, the rest on `OfferPeace`). 42 is taken
for the widest leader-to-challenger gap (0.207 against a 0.05 margin) and
for not being the default seed, since a test that only passes on the seed
everything else uses proves less.

Changing behaviour means re-measuring this, not guessing; the sweep prints
what is missing.
"""

PLAN_ONLY = frozenset({"MoveTo"})
"""Skills the brain is never meant to choose - a plan names them or nobody does."""


class Run:
    """One world, ticked, with everything worth asserting about it collected."""

    def __init__(self, seed: int = SEED, population: int = 70) -> None:
        config = WorldConfig(
            seed=seed,
            population=population,
            max_agents=200,
            terrain=TerrainConfig(resolution=64, size=240.0),
        )
        self.world: World = IslandWorldBuilder().build(config)
        self.minds = MindRegistry()
        self.ledger = SocialLedger()
        self.skills: SkillRegistry = build_registry(
            SkillServices(minds=self.minds, ledger=self.ledger)
        )
        pipeline = build_pipeline(self.minds, self.skills, temperature=0.35, ledger=self.ledger)

        every = list(self.skills.all())
        self.wanted: set[str] = set()
        self.events: set[EventType] = set()
        self.roles: set[TribeRole] = set()
        self.best_challenge = -1.0
        self.pacts = 0

        for _ in range(TICKS):
            pipeline.step(self.world, self.world.clock.dt)
            self.world.clock = self.world.clock.advance()
            for event in self.world.events.drain():
                self.events.add(event.type)

            unseen = [skill for skill in every if type(skill).name not in self.wanted]
            for agent in self.world.living_agents():
                self.roles.add(agent.role)
                if not unseen:
                    continue
                mind = self.minds.require(agent.id)
                context = DecisionContext(
                    agent=agent,
                    world=self.world,
                    memory=mind.memory,
                    observation=mind.observation,
                )
                for skill in unseen:
                    if skill.utility(agent, context) > 0.0:
                        self.wanted.add(type(skill).name)

            self._measure_challengers()

    def _measure_challengers(self) -> None:
        """Track how close the best-placed rival ever got to the leader."""
        for tribe in self.world.tribes.values():
            self.pacts += len(tribe.allied_with)
            leader = self.world.agents.get(tribe.leader_id) if tribe.leader_id else None
            if leader is None or not leader.alive:
                continue
            theirs = legitimacy(self.world, leader, tribe, self.minds)
            for member_id in tribe.member_ids:
                if member_id == leader.id or member_id not in self.world.agents:
                    continue
                mine = legitimacy(self.world, self.world.agents[member_id], tribe, self.minds)
                self.best_challenge = max(self.best_challenge, mine - theirs)


@pytest.fixture(scope="module")
def run() -> Run:
    """One shared 6,000-tick world: ticking it is the expensive part."""
    return Run()


def test_a_society_forms_at_all(run: Run) -> None:
    """If this fails the rest of the file is measuring nothing."""
    assert len(run.world.living_agents()) > 20, "the island died; nothing below is meaningful"
    assert len(run.world.tribes) >= 2, "no tribes formed, so no tribe skill could have run"


def test_every_skill_the_brain_can_pick_is_wanted_by_somebody(run: Run) -> None:
    """The sweep that found `Raid`: a skill nobody ever wants is dead code.

    A skill may legitimately be rare. It may not be impossible: if nobody
    scores it above zero across 6,000 ticks of a whole society, either its
    arithmetic is wrong or its preconditions can never hold together, and
    both deserve a look rather than a passing suite.
    """
    every = {type(skill).name for skill in run.skills.all()} - PLAN_ONLY
    never = sorted(every - run.wanted)

    assert not never, f"registered, tested, and never once wanted: {never}"


def test_the_rare_social_machinery_actually_turns(run: Run) -> None:
    """Tribes form, fall out and make up - two of these were once impossible."""
    assert EventType.TRIBE_FOUNDED in run.events
    assert EventType.TRIBE_JOINED in run.events
    assert EventType.COUP in run.events, "nobody ever challenged a leader"
    assert run.pacts > 0, "no two tribes ever signed a pact"


def test_a_challenger_reaches_a_winnable_position(run: Run) -> None:
    """`COUP_MARGIN` once sat outside the entire observed legitimacy spread.

    The old 0.25 was unreachable: the best-placed rival in a whole world
    never came within 0.04 of it. This asserts the property that was false
    then and is true now - somebody, at some point, stands far enough above
    their leader to take the tribe.
    """
    assert run.best_challenge > COUP_MARGIN, (
        f"the best challenger in 6,000 ticks got {run.best_challenge:+.3f} above their "
        f"leader, against a margin of {COUP_MARGIN}: no coup could ever succeed"
    )


def test_a_deposed_leader_becomes_an_elder(run: Run) -> None:
    """`TribeRole.ELDER` is assigned on exactly one path, and never was."""
    assert run.ledger.coups > 0, (
        f"{run.ledger.coup_attempts} coups attempted and none won; "
        "the chosen seed is meant to produce one"
    )
    assert TribeRole.ELDER in run.roles, "a coup was won and nobody was deposed into an elder"
