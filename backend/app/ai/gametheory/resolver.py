"""Running an encounter: context picks the game, strategies pick the moves.

Payoffs are the score; the *consequences* are what the agents actually feel.
Food is always transferred, never created - a Prisoner's Dilemma over a meal
has to move the meal from one inventory to another, or cooperation would be
free and the whole dilemma would evaporate.
"""

from app.ai import social
from app.ai.gametheory.encounters import EncounterResult, GameKind, PayoffMatrix
from app.ai.gametheory.payoffs import PayoffConfig
from app.ai.gametheory.strategies import Move, StrategyContext, StrategyRegistry
from app.ai.minds import Mind, MindRegistry
from app.sim import balance
from app.sim.entities import Agent, ResourceKind, ResourceNode
from app.sim.events import EventType, SimEvent
from app.sim.world import World

SHARE_AMOUNT = 1.0
"""Food handed over when someone shares."""

STEAL_AMOUNT = 1.5
"""Food taken when someone defects on a sharer - more than a fair share."""

SCUFFLE_DAMAGE = 1.5
HAWK_INJURY = 6.0
CONTEST_FOOD = 1.0

HUNGRY_BELOW = 55.0
SURPLUS_FOOD = 1.0
STAG_RADIUS = 14.0


class EncounterResolver:
    """Chooses a game for a pair, asks both strategies, applies the payoffs."""

    __slots__ = ("_minds", "_payoffs", "_strategies")

    def __init__(
        self,
        payoffs: PayoffConfig,
        strategies: StrategyRegistry,
        minds: MindRegistry,
    ) -> None:
        self._payoffs = payoffs
        self._strategies = strategies
        self._minds = minds

    # ------------------------------------------------------------ selection

    def pick_game(self, world: World, a: Agent, b: Agent) -> GameKind | None:
        """Return the game this meeting is, or `None` if it is just a meeting.

        Order matters: a shared opportunity (the deer) outranks a dispute over
        food, which outranks a squabble over a bush.
        """
        a_hungry = a.needs.hunger < HUNGRY_BELOW
        b_hungry = b.needs.hunger < HUNGRY_BELOW

        if a_hungry and b_hungry and self._deer_nearby(world, a):
            return GameKind.STAG_HUNT

        a_surplus = a.inventory.food >= SURPLUS_FOOD
        b_surplus = b.inventory.food >= SURPLUS_FOOD
        if (a_surplus and b_hungry) or (b_surplus and a_hungry):
            return GameKind.PRISONERS_DILEMMA

        # Both reaching for the same thing.
        if a.current_skill == b.current_skill and a.current_skill in {"Gather", "HuntRabbit"}:
            return GameKind.HAWK_DOVE

        return None

    @staticmethod
    def _deer_nearby(world: World, agent: Agent) -> bool:
        """Whether big game is close enough to be worth two hunters."""
        x, z = agent.position
        for node_id in world.resource_index.query_radius(x, z, STAG_RADIUS):
            node = world.resources.get(node_id)
            if node is not None and node.kind is ResourceKind.DEER and not node.depleted:
                return True
        return False

    # -------------------------------------------------------------- resolve

    def resolve(self, world: World, a: Agent, b: Agent) -> EncounterResult | None:
        """Play one round between `a` and `b`, applying every consequence."""
        game = self.pick_game(world, a, b)
        if game is None:
            return None

        mind_a = self._minds.require(a.id)
        mind_b = self._minds.require(b.id)
        matrix = self._payoffs.matrix(game)
        rng = world.rngs["encounter"]

        move_a = self._move(a, b, mind_a, matrix, float(rng.random()))
        move_b = self._move(b, a, mind_b, matrix, float(rng.random()))

        # Trembling hand: the occasional slip is what keeps forgiving
        # strategies meaningfully different from naive ones.
        trembled = False
        if float(rng.random()) < self._payoffs.trembling_hand:
            move_a = _flip(move_a)
            trembled = True
        if float(rng.random()) < self._payoffs.trembling_hand:
            move_b = _flip(move_b)
            trembled = True

        payoff_a = matrix.payoff(move_a, move_b)
        payoff_b = matrix.payoff(move_b, move_a)

        betrayers = self._betrayers(a, b, mind_a, mind_b, move_a, move_b)
        food_moved, summary = self._apply(world, game, a, b, move_a, move_b)

        result = EncounterResult(
            game=game,
            agent_a=a.id,
            agent_b=b.id,
            move_a=move_a,
            move_b=move_b,
            payoff_a=payoff_a,
            payoff_b=payoff_b,
            trembled=trembled,
            betrayal_by=betrayers,
            food_moved=food_moved,
            summary=summary,
        )
        self._remember(world, a, b, mind_a, mind_b, result)
        self._emit(world, a, b, result)
        return result

    # --------------------------------------------------------------- pieces

    def _move(
        self,
        agent: Agent,
        other: Agent,
        mind: Mind,
        matrix: PayoffMatrix,
        roll: float,
    ) -> Move:
        """Ask this agent's inherited strategy for a move."""
        relationship = mind.memory.social.get(other.id)
        strategy = self._strategies.require(agent.strategy)
        context = StrategyContext(
            own_moves=tuple(Move(m) for m in relationship.own_moves) if relationship else (),
            partner_moves=tuple(Move(m) for m in relationship.moves) if relationship else (),
            own_payoffs=tuple(relationship.payoffs) if relationship else (),
            trust=relationship.trust if relationship else 0.0,
            reputation=social.effective_opinion(mind.memory, other.id),
            greed=agent.traits.greed,
            honesty=agent.traits.honesty,
            advantage=social.relative_advantage(agent, other),
            roll=roll,
            reward=matrix.reward,
        )
        return strategy.move(context)

    @staticmethod
    def _betrayers(
        a: Agent,
        b: Agent,
        mind_a: Mind,
        mind_b: Mind,
        move_a: Move,
        move_b: Move,
    ) -> tuple[int, ...]:
        """Who defected on a partner that actually trusted them."""
        betrayers: list[int] = []
        rel_b_of_a = mind_b.memory.social.get(a.id)
        rel_a_of_b = mind_a.memory.social.get(b.id)
        if move_a is Move.DEFECT and rel_b_of_a is not None and social.is_betrayal(rel_b_of_a):
            betrayers.append(a.id)
        if move_b is Move.DEFECT and rel_a_of_b is not None and social.is_betrayal(rel_a_of_b):
            betrayers.append(b.id)
        return tuple(betrayers)

    def _apply(
        self,
        world: World,
        game: GameKind,
        a: Agent,
        b: Agent,
        move_a: Move,
        move_b: Move,
    ) -> tuple[float, str]:
        """Turn the moves into food, health and a human-readable line."""
        match game:
            case GameKind.PRISONERS_DILEMMA:
                return self._apply_dilemma(a, b, move_a, move_b)
            case GameKind.STAG_HUNT:
                return self._apply_stag_hunt(world, a, b, move_a, move_b)
            case GameKind.HAWK_DOVE:
                return self._apply_hawk_dove(a, b, move_a, move_b)
            case _:
                return 0.0, f"{a.name} and {b.name} sized each other up"

    @staticmethod
    def _apply_dilemma(a: Agent, b: Agent, move_a: Move, move_b: Move) -> tuple[float, str]:
        """Share, hoard or steal. Food only ever moves between the two."""
        if move_a is Move.COOPERATE and move_b is Move.COOPERATE:
            # Pool and level up: the richer one tops the poorer one up.
            richer, poorer = (a, b) if a.inventory.food >= b.inventory.food else (b, a)
            moved = min(SHARE_AMOUNT, max(0.0, (richer.inventory.food - poorer.inventory.food) / 2))
            richer.inventory.food -= moved
            poorer.inventory.food += moved
            return moved, f"{a.name} and {b.name} shared food"

        if move_a is Move.DEFECT and move_b is Move.DEFECT:
            a.health = max(1.0, a.health - SCUFFLE_DAMAGE)
            b.health = max(1.0, b.health - SCUFFLE_DAMAGE)
            return 0.0, f"{a.name} and {b.name} both grabbed, and both lost"

        taker, giver = (a, b) if move_a is Move.DEFECT else (b, a)
        moved = min(STEAL_AMOUNT, giver.inventory.food)
        giver.inventory.food -= moved
        taker.inventory.food += moved
        return moved, f"{taker.name} took food from {giver.name}"

    @staticmethod
    def _apply_stag_hunt(
        world: World,
        a: Agent,
        b: Agent,
        move_a: Move,
        move_b: Move,
    ) -> tuple[float, str]:
        """Bring down the deer together, or settle for rabbits apart."""
        if move_a is Move.COOPERATE and move_b is Move.COOPERATE:
            deer = _nearest_kind(world, a, ResourceKind.DEER, STAG_RADIUS)
            if deer is not None:
                deer.amount = 0.0
                share = balance.DEER_FOOD / 2.0
                a.inventory.food += share
                b.inventory.food += share
                return balance.DEER_FOOD, f"{a.name} and {b.name} brought down a deer together"
            return 0.0, f"{a.name} and {b.name} hunted, but the deer was gone"

        if move_a is Move.DEFECT and move_b is Move.DEFECT:
            a.inventory.food += balance.RABBIT_FOOD / 2.0
            b.inventory.food += balance.RABBIT_FOOD / 2.0
            return 0.0, f"{a.name} and {b.name} each chased rabbits instead"

        defector, waiter = (a, b) if move_a is Move.DEFECT else (b, a)
        defector.inventory.food += balance.RABBIT_FOOD
        return 0.0, f"{defector.name} abandoned the hunt, leaving {waiter.name} empty-handed"

    @staticmethod
    def _apply_hawk_dove(a: Agent, b: Agent, move_a: Move, move_b: Move) -> tuple[float, str]:
        """Fight or yield over the same patch."""
        if move_a is Move.DEFECT and move_b is Move.DEFECT:
            a.health = max(1.0, a.health - HAWK_INJURY)
            b.health = max(1.0, b.health - HAWK_INJURY)
            return 0.0, f"{a.name} and {b.name} fought over a find, and both bled"

        if move_a is Move.COOPERATE and move_b is Move.COOPERATE:
            return 0.0, f"{a.name} and {b.name} shared the patch"

        hawk, dove = (a, b) if move_a is Move.DEFECT else (b, a)
        moved = min(CONTEST_FOOD, dove.inventory.food)
        dove.inventory.food -= moved
        hawk.inventory.food += moved
        return moved, f"{dove.name} backed down and let {hawk.name} take the find"

    def _remember(
        self,
        world: World,
        a: Agent,
        b: Agent,
        mind_a: Mind,
        mind_b: Mind,
        result: EncounterResult,
    ) -> None:
        """Write the round into both memories and move trust accordingly."""
        tick = world.clock.tick
        seconds = world.clock.sim_seconds

        for _actor, other, mind, own, theirs, payoff in (
            (a, b, mind_a, result.move_a, result.move_b, result.payoff_a),
            (b, a, mind_b, result.move_b, result.move_a, result.payoff_b),
        ):
            relationship = social.record_round(
                mind.memory, other.id, own.value, theirs.value, payoff, tick
            )
            if theirs is Move.COOPERATE:
                social.adjust_trust(relationship, social.COOPERATION_TRUST)
            elif other.id in result.betrayal_by:
                social.adjust_trust(relationship, social.BETRAYAL_TRUST)
                relationship.betrayals += 1
            else:
                social.adjust_trust(relationship, social.DEFECTION_TRUST)

            social.remember(
                mind.memory,
                tick=tick,
                sim_seconds=seconds,
                event_type=EventType.ENCOUNTER,
                summary=result.summary,
                actors=(other.id,),
                importance=7 if other.id in result.betrayal_by else 4,
            )

    @staticmethod
    def _emit(world: World, a: Agent, b: Agent, result: EncounterResult) -> None:
        """Announce the encounter to the event feed, if it is worth announcing."""
        if result.betrayal_by:
            kind, importance = EventType.BETRAYAL, 8
        elif result.mutual_cooperation:
            kind, importance = EventType.COOPERATION, 3
        elif result.cooperations == 0 and result.game is GameKind.HAWK_DOVE:
            kind, importance = EventType.COMBAT, 6
        else:
            kind, importance = EventType.DEFECTION, 5

        world.events.emit(
            SimEvent(
                tick=world.clock.tick,
                type=kind,
                summary=result.summary,
                actors=(a.id, b.id),
                importance=importance,
                position=a.position,
                data={
                    "game": result.game.value,
                    "moves": f"{result.move_a.value}{result.move_b.value}",
                    "trembled": result.trembled,
                },
            )
        )


def _flip(move: Move) -> Move:
    """Return the other move."""
    return Move.DEFECT if move is Move.COOPERATE else Move.COOPERATE


def _nearest_kind(
    world: World,
    agent: Agent,
    kind: ResourceKind,
    radius: float,
) -> ResourceNode | None:
    """Return the nearest live node of `kind`, or `None`."""
    x, z = agent.position
    for node_id in sorted(world.resource_index.query_radius(x, z, radius)):
        node = world.resources.get(node_id)
        if node is not None and node.kind is kind and not node.depleted:
            return node
    return None
