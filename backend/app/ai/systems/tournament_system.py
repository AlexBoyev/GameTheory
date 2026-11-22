"""Axelrod's tournament, run inside the simulation (SPEC section 5.3).

Survival is off here. Every agent meets every other agent in an iterated
Prisoner's Dilemma, carries its total score, and at the end of each generation
the population is resampled in proportion to what each *strategy* earned -
replicator dynamics. Run it for twenty generations and you can watch the mix
move: Tit-for-Tat climbing, AlwaysDefect spiking early and then starving as
its victims disappear.

It is a system rather than a script because that is what makes it watchable:
the same engine, the same frames, the same charts and inspector as the island,
so the strategy-share chart *is* the tournament result.

Two deliberate differences from the island:

* Pairings are exhaustive and scheduled, not spatial. Agents stand in a ring
  and never move; who meets whom is round-robin, so no strategy can benefit
  from being lucky about its neighbours.
* The payoff is the score and nothing else. No food changes hands, nobody
  starves, nobody is born - a tournament measures strategies, and survival
  pressure would measure something else as well.
"""

import math

import structlog

from app.ai.gametheory.encounters import GameKind, PayoffMatrix
from app.ai.gametheory.ledger import SocialLedger
from app.ai.gametheory.payoffs import PayoffConfig
from app.ai.gametheory.strategies import Move, StrategyContext, StrategyRegistry
from app.ai.minds import MindRegistry
from app.core.world_config import StrategyName
from app.sim.entities import Agent, AgentState
from app.sim.events import EventType, SimEvent
from app.sim.world import World

LOG = structlog.get_logger(__name__)

ROUNDS_PER_PAIR = 10
"""Iterated, not one-shot: a single round cannot tell Tit-for-Tat from a
pushover, and reciprocity needs a future to pay off in."""

PAIRINGS_PER_TICK = 24
"""How many pairs are resolved per tick. Keeps a 100-agent tournament
watchable (about 200 ticks a generation) instead of over in one frame."""

GENERATIONS = 20
"""After this many, the tournament stops and the final mix stands."""

SELECTION_STRENGTH = 4.0
"""How sharply score is converted into next-generation share.

Weights are `exp(strength * (score - best))`, so the leader keeps a weight of
1 and a strategy half a point behind keeps `exp(-2)`, about an eighth. Plain
proportional selection is too flat to show anything here: scores land between
2.0 and 2.7, which is a 1.35:1 advantage, and over twenty generations of a
hundred agents drift drowns it. This is still a replicator - the gradient is
just steep enough to see.
"""


class TournamentState:
    """Scores, the pairing schedule, and which generation we are in.

    Lives beside the world rather than inside it: a tournament is a thing
    being *run on* a world, and `sim/` has no business knowing about it.
    """

    __slots__ = ("finished", "generation", "pair_index", "pairs", "rounds", "scores")

    def __init__(self) -> None:
        self.scores: dict[int, float] = {}
        self.rounds: dict[int, int] = {}
        self.pairs: list[tuple[int, int]] = []
        self.pair_index = 0
        self.generation = 0
        self.finished = False

    def reset_for(self, agent_ids: list[int]) -> None:
        """Start a fresh generation over `agent_ids`."""
        self.scores = dict.fromkeys(agent_ids, 0.0)
        self.rounds = dict.fromkeys(agent_ids, 0)
        self.pairs = [
            (first, second)
            for index, first in enumerate(agent_ids)
            for second in agent_ids[index + 1 :]
        ]
        self.pair_index = 0

    @property
    def complete(self) -> bool:
        """True when every pairing in this generation has been played."""
        return self.pair_index >= len(self.pairs)

    def average_by_strategy(self, world: World) -> dict[str, float]:
        """Mean score per round, by strategy - the tournament standings.

        Per *round* rather than per agent, so a strategy is not rewarded for
        happening to have more members in this generation.
        """
        totals: dict[str, float] = {}
        rounds: dict[str, int] = {}
        for agent_id, score in self.scores.items():
            agent = world.agents.get(agent_id)
            if agent is None:
                continue
            totals[agent.strategy] = totals.get(agent.strategy, 0.0) + score
            rounds[agent.strategy] = rounds.get(agent.strategy, 0) + self.rounds.get(agent_id, 0)
        return {
            name: round(total / rounds[name], 4)
            for name, total in totals.items()
            if rounds.get(name, 0) > 0
        }


class TournamentSystem:
    """Plays the schedule, then evolves the population between generations."""

    name = "tournament"

    __slots__ = (
        "_ledger",
        "_minds",
        "_payoffs",
        "_strategies",
        "generations",
        "pairings_per_tick",
        "rounds_per_pair",
        "state",
    )

    def __init__(
        self,
        minds: MindRegistry,
        strategies: StrategyRegistry,
        payoffs: PayoffConfig,
        ledger: SocialLedger,
        rounds_per_pair: int = ROUNDS_PER_PAIR,
        pairings_per_tick: int = PAIRINGS_PER_TICK,
        generations: int = GENERATIONS,
    ) -> None:
        self._minds = minds
        self._strategies = strategies
        self._payoffs = payoffs
        self._ledger = ledger
        self.rounds_per_pair = rounds_per_pair
        self.pairings_per_tick = pairings_per_tick
        self.generations = generations
        self.state = TournamentState()

    def on_world_replaced(self, world: World) -> None:
        """Forget the old tournament; this is a different one."""
        self.state = TournamentState()
        _ = world

    def step(self, world: World, dt: float) -> None:
        """Resolve this tick's share of the schedule."""
        _ = dt
        if not world.config.tournament_mode or self.state.finished:
            return

        agents = world.living_agents()
        if len(agents) < 2:
            return

        if not self.state.pairs:
            self.state.reset_for([agent.id for agent in agents])

        matrix = self._payoffs.matrix(GameKind.PRISONERS_DILEMMA)
        played = 0
        while played < self.pairings_per_tick and not self.state.complete:
            first_id, second_id = self.state.pairs[self.state.pair_index]
            self.state.pair_index += 1
            first = world.agents.get(first_id)
            second = world.agents.get(second_id)
            if first is None or second is None:
                continue
            self._play_pair(world, first, second, matrix)
            played += 1

        if self.state.complete:
            self._end_generation(world)

    # ------------------------------------------------------------ one pair

    def _play_pair(self, world: World, first: Agent, second: Agent, matrix: PayoffMatrix) -> None:
        """Play `rounds_per_pair` iterated rounds and bank both scores."""
        own_moves: list[Move] = []
        their_moves: list[Move] = []
        own_payoffs: list[float] = []
        their_payoffs: list[float] = []
        rng = world.rngs["encounter"]
        payoff_of = matrix.payoff
        reward = matrix.reward
        first_strategy = self._strategies.require(first.strategy)
        second_strategy = self._strategies.require(second.strategy)

        for _ in range(self.rounds_per_pair):
            first_move = first_strategy.move(
                StrategyContext(
                    own_moves=tuple(own_moves),
                    partner_moves=tuple(their_moves),
                    own_payoffs=tuple(own_payoffs),
                    greed=first.traits.greed,
                    honesty=first.traits.honesty,
                    roll=float(rng.random()),
                    reward=reward,
                )
            )
            second_move = second_strategy.move(
                StrategyContext(
                    own_moves=tuple(their_moves),
                    partner_moves=tuple(own_moves),
                    own_payoffs=tuple(their_payoffs),
                    greed=second.traits.greed,
                    honesty=second.traits.honesty,
                    roll=float(rng.random()),
                    reward=reward,
                )
            )

            first_score = payoff_of(first_move, second_move)
            second_score = payoff_of(second_move, first_move)
            own_moves.append(first_move)
            their_moves.append(second_move)
            own_payoffs.append(first_score)
            their_payoffs.append(second_score)

            self.state.scores[first.id] = self.state.scores.get(first.id, 0.0) + first_score
            self.state.scores[second.id] = self.state.scores.get(second.id, 0.0) + second_score
            self.state.rounds[first.id] = self.state.rounds.get(first.id, 0) + 1
            self.state.rounds[second.id] = self.state.rounds.get(second.id, 0) + 1

            self._ledger.rounds[GameKind.PRISONERS_DILEMMA.value] += 1
            for move in (first_move, second_move):
                if move is Move.COOPERATE:
                    self._ledger.cooperations[GameKind.PRISONERS_DILEMMA.value] += 1
                else:
                    self._ledger.defections[GameKind.PRISONERS_DILEMMA.value] += 1

        # Visible in the scene: a pair mid-match is talking, not idling.
        for agent in (first, second):
            agent.state = AgentState.TALK

    # ------------------------------------------------- between generations

    def _end_generation(self, world: World) -> None:
        """Resample strategies in proportion to score, then start again."""
        standings = self.state.average_by_strategy(world)
        self.state.generation += 1

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=EventType.GOD_ACTION,
                summary=(
                    f"Generation {self.state.generation}: "
                    + ", ".join(
                        f"{name} {score:.2f}"
                        for name, score in sorted(standings.items(), key=lambda item: -item[1])[:3]
                    )
                ),
                importance=9,
                data={"tournament": True, "generation": self.state.generation},
            )
        )
        LOG.info("tournament.generation", generation=self.state.generation, standings=standings)

        if self.state.generation >= self.generations:
            self.state.finished = True
            return

        self.evolve(world, standings)
        self.state.reset_for([agent.id for agent in world.living_agents()])

    def evolve(self, world: World, standings: dict[str, float]) -> None:
        """Reassign every agent's strategy, weighted by this generation's scores.

        Public because it is the replicator step itself - the one piece of
        this system worth asserting on directly, rather than through four
        hundred ticks of schedule.

        Replicator dynamics with the population held constant: nobody dies,
        they simply change their mind in proportion to what paid. Every
        strategy keeps a small non-zero share, because one bad generation
        permanently removing a strategy would stop the tournament being a
        comparison at all.
        """
        if not standings:
            return
        names: list[StrategyName] = list(standings)  # type: ignore[arg-type]
        best = max(standings.values())
        weights = [math.exp(SELECTION_STRENGTH * (standings[name] - best)) for name in names]
        total = sum(weights)
        shares = [weight / total for weight in weights]

        rng = world.rngs["decide"]
        draws = rng.choice(len(names), size=len(world.living_agents()), p=shares)
        for agent, draw in zip(world.living_agents(), draws, strict=False):
            agent.strategy = names[int(draw)]
            # A new strategy is a new agent as far as history goes; keeping
            # the old pair history would let a defector inherit a reputation
            # for cooperating.
            mind = self._minds.get(agent.id)
            if mind is not None:
                mind.memory.social.clear()
