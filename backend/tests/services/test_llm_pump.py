"""The bridge between the engine thread and the model (ADR 0004).

The contract being tested is "the simulation never waits": every failure mode
here - a dead provider, prose instead of JSON, a world reset mid-flight - has
to end with the agent back in play and the pump still running.
"""

import asyncio

import pytest

from app.ai.llm.broker import Delivery, IntentionBroker, PendingRequest
from app.ai.llm.context import PromptContext
from app.ai.llm.gateway import LLMGateway
from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.provider import LLMError
from app.ai.llm.schemas import Intention, LLMRequest, LLMResponse
from app.core.settings import Settings
from app.services.llm_pump import LLMPump, cache_key

AN_INTENTION = Intention(
    thought="They trust me enough to follow.",
    goal="lead them",
    plan=[{"skill": "FoundTribe", "params": {}}],
    say="Someone has to decide.",
).model_dump_json()


def a_context(agent_id: int = 1, kind: str = "intention") -> PromptContext:
    """A context complete enough for `intention.j2` to render."""
    return PromptContext(
        agent_id=agent_id,
        kind=kind,
        context={
            "agent": {
                "name": "Mira",
                "age": 24.0,
                "strategy": "TitForTat",
                "traits": {"charisma": 0.8, "greed": 0.2},
                "needs": {"hunger": 60.0, "thirst": 80.0},
                "inventory": {"food": 2.0, "wood": 0.0},
                "tribe": None,
                "role": "none",
            },
            "clock": {"day": 2, "season": "spring", "is_night": False},
            "nearby": [{"name": "Bo", "trust": 0.4}],
            "relationships": [{"name": "Bo", "trust": 0.4, "is_ally": False, "caught_lying": 0}],
            "memories": [{"summary": "Bo shared food with me", "day": 1}],
            "skills": [{"name": "Gather", "description": "Pick berries.", "params_hint": ""}],
            "max_steps": 3,
            "max_beliefs": 5,
        },
    )


def a_request(agent_id: int = 1, world_uid: int = 1, kind: str = "intention") -> PendingRequest:
    """A posted deliberation."""
    return PendingRequest(context=a_context(agent_id, kind), world_uid=world_uid, issued_sim_s=10.0)


class ScriptedProvider:
    """A provider that returns, in order, whatever it was given."""

    name = "scripted"

    def __init__(self, *replies: str | Exception) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return "scripted-1"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.prompts.append(request.prompt)
        reply = self.replies.pop(0) if self.replies else AN_INTENTION
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            agent_id=request.agent_id,
            kind=request.kind,
            content=reply,
            model=self.model,
            provider=self.name,
        )

    async def healthy(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def a_pump(settings: Settings, provider: object) -> tuple[LLMPump, IntentionBroker]:
    """A pump over a fresh broker and a given provider."""
    broker = IntentionBroker()
    gateway = LLMGateway(settings, provider)  # type: ignore[arg-type]
    return LLMPump(broker, gateway, idle_sleep_s=0.01), broker


# ------------------------------------------------------------------- broker


def test_the_broker_refuses_a_second_request_for_the_same_agent() -> None:
    """One deliberation per agent at a time, or the queue fills with one voice."""
    broker = IntentionBroker()

    assert broker.post(a_request(agent_id=5)) is True
    assert broker.post(a_request(agent_id=5)) is False
    assert broker.post(a_request(agent_id=6)) is True
    assert broker.pending_count == 2


def test_delivering_frees_the_agent_to_ask_again() -> None:
    broker = IntentionBroker()
    broker.post(a_request(agent_id=5))
    broker.take_pending()

    assert broker.inflight_count == 1
    broker.deliver(Delivery(agent_id=5, world_uid=1))

    assert broker.inflight_count == 0
    assert broker.post(a_request(agent_id=5)) is True


def test_the_broker_drops_the_oldest_when_the_model_cannot_keep_up() -> None:
    """Back-pressure: a stale situation is worse than no intention at all."""
    broker = IntentionBroker(max_pending=2)

    for agent_id in range(5):
        broker.post(a_request(agent_id=agent_id))

    assert broker.pending_count == 2
    waiting = [item.context.agent_id for item in broker.take_pending(limit=10)]
    assert waiting == [3, 4], "the newest situations survive"


def test_clearing_the_broker_empties_both_directions() -> None:
    broker = IntentionBroker()
    broker.post(a_request(agent_id=1))
    broker.deliver(Delivery(agent_id=2, world_uid=1))

    broker.clear()

    assert broker.pending_count == 0
    assert broker.collect() == []
    assert broker.inflight_count == 0


# --------------------------------------------------------------------- pump


async def test_the_pump_turns_a_reply_into_an_intention(settings: Settings) -> None:
    pump, broker = a_pump(settings, ScriptedProvider(AN_INTENTION))
    broker.post(a_request())

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    delivered = broker.collect()
    assert len(delivered) == 1
    assert delivered[0].intention is not None
    assert delivered[0].intention.goal == "lead them"
    assert delivered[0].error is None


async def test_the_pump_strips_the_code_fences_models_add(settings: Settings) -> None:
    fenced = f"```json\n{AN_INTENTION}\n```"
    pump, broker = a_pump(settings, ScriptedProvider(fenced))
    broker.post(a_request())

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    assert broker.collect()[0].intention is not None


async def test_bad_json_gets_exactly_one_repair_attempt(settings: Settings) -> None:
    provider = ScriptedProvider("I think I will go and find some berries.", AN_INTENTION)
    pump, broker = a_pump(settings, provider)
    broker.post(a_request())

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    assert len(provider.prompts) == 2, "one call, then one repair"
    assert "not valid JSON" in provider.prompts[1]
    assert broker.collect()[0].intention is not None


async def test_a_model_that_never_produces_json_is_given_up_on(settings: Settings) -> None:
    provider = ScriptedProvider("nope", "still nope", AN_INTENTION)
    pump, broker = a_pump(settings, provider)
    broker.post(a_request())

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    assert len(provider.prompts) == 2, "two attempts, not three"
    delivery = broker.collect()[0]
    assert delivery.intention is None
    assert delivery.error == "unparseable reply"


async def test_a_dead_provider_delivers_an_error_not_an_exception(settings: Settings) -> None:
    pump, broker = a_pump(settings, ScriptedProvider(LLMError("daemon is not running")))
    broker.post(a_request())

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    delivery = broker.collect()[0]
    assert delivery.intention is None
    assert "daemon is not running" in (delivery.error or "")
    assert broker.inflight_count == 0, "the agent must be free to try again"


async def test_a_reflection_comes_back_as_beliefs(settings: Settings) -> None:
    reflection = '{"beliefs":["Rex steals - avoid him"],"summary":"Hungry days."}'
    pump, broker = a_pump(settings, ScriptedProvider(reflection))
    broker.post(a_request(kind="reflection"))

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending()))

    delivery = broker.collect()[0]
    assert delivery.reflection is not None
    assert delivery.reflection.beliefs == ["Rex steals - avoid him"]
    assert delivery.intention is None


async def test_the_pump_keeps_running_after_a_bad_batch(settings: Settings) -> None:
    """One agent's broken reply must not stop everyone else deliberating."""
    pump, broker = a_pump(settings, ScriptedProvider(LLMError("boom"), AN_INTENTION))
    broker.post(a_request(agent_id=1))
    broker.post(a_request(agent_id=2))

    await asyncio.gather(*(pump._handle(item) for item in broker.take_pending(limit=2)))

    results = {item.agent_id: item for item in broker.collect()}
    assert results[1].error is not None
    assert results[2].intention is not None


async def test_the_pump_runs_as_a_task_and_stops_cleanly(settings: Settings) -> None:
    pump, broker = a_pump(settings, MockProvider())
    pump.start()
    broker.post(a_request())

    for _ in range(100):
        await asyncio.sleep(0.01)
        if broker.collect():
            break
    else:
        pytest.fail("the pump never delivered anything")

    await pump.stop()
    assert pump.running is False


async def test_a_disabled_gateway_deliberates_for_nobody(settings: Settings) -> None:
    pump, broker = a_pump(settings, MockProvider())
    pump._gateway.set_enabled(False)
    pump.start()
    broker.post(a_request())

    await asyncio.sleep(0.05)

    assert broker.collect() == []
    assert broker.pending_count == 1, "the request waits rather than being thrown away"
    await pump.stop()


# ------------------------------------------------------------------- caching


def test_the_cache_key_depends_on_prompt_and_model() -> None:
    assert cache_key("a", "m1") == cache_key("a", "m1")
    assert cache_key("a", "m1") != cache_key("b", "m1")
    assert cache_key("a", "m1") != cache_key("a", "m2")
