"""The deliberative layer: provider, scheduler limits, and the breaker.

Every test here runs with no Ollama installed - either against `MockProvider`
or against a faked daemon (respx). That is the point: the app has to work with
nothing pulled, so its tests must too.
"""

import asyncio

import httpx
import pytest
import respx

from app.ai.llm.gateway import LLMGateway
from app.ai.llm.mock_provider import MockProvider
from app.ai.llm.ollama_provider import CHAT_PATH, TAGS_PATH, OllamaProvider
from app.ai.llm.provider import LLMError, LLMProvider
from app.ai.llm.scheduler import LLMScheduler, SchedulerLimits
from app.ai.llm.schemas import Intention, LLMRequest, LLMResponse
from app.ai.llm.telemetry import CircuitBreaker
from app.core.settings import Settings

OLLAMA_URL = "http://localhost:11434"


def request(agent_id: int = 1, prompt: str = "what now?", **extra: object) -> LLMRequest:
    """A minimal request."""
    return LLMRequest(agent_id=agent_id, prompt=prompt, **extra)  # type: ignore[arg-type]


def chat_reply(content: str, **extra: object) -> httpx.Response:
    """A successful `/api/chat` response."""
    return httpx.Response(200, json={"message": {"content": content}, "done": True, **extra})


def an_intention(goal: str = "stay fed", skill: str = "Gather") -> str:
    """A valid `Intention` as JSON."""
    return Intention(
        thought="I am hungry.",
        goal=goal,
        plan=[{"skill": skill, "params": {}}],  # type: ignore[list-item]
    ).model_dump_json()


# ------------------------------------------------------------- mock provider


async def test_the_mock_provider_needs_nothing_installed() -> None:
    provider = MockProvider()

    assert await provider.healthy()
    response = await provider.generate(request())

    assert response.ok
    assert Intention.model_validate_json(response.content).plan


async def test_the_mock_provider_is_deterministic() -> None:
    """Same agent, same prompt, same plan - or the determinism test is a lie."""
    first = await MockProvider().generate(request(agent_id=7, prompt="x"))
    second = await MockProvider().generate(request(agent_id=7, prompt="x"))

    assert first.content == second.content


# ----------------------------------------------------------- ollama provider


@respx.mock
async def test_ollama_sends_the_schema_and_returns_the_content() -> None:
    route = respx.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(return_value=chat_reply(an_intention()))
    provider = OllamaProvider(base_url=OLLAMA_URL, model="qwen3:8b")

    response = await provider.generate(
        request(json_schema=Intention.model_json_schema(), system="be brief")
    )

    assert response.ok
    assert response.provider == "ollama"
    body = route.calls.last.request.read().decode()
    assert '"format"' in body, "constrained decoding is what makes valid JSON the norm"
    assert '"stream":false' in body
    assert '"role":"system"' in body
    await provider.aclose()


@respx.mock
async def test_ollama_turns_a_timeout_into_an_llm_error() -> None:
    respx.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(side_effect=httpx.ConnectTimeout("too slow"))
    provider = OllamaProvider(base_url=OLLAMA_URL)

    with pytest.raises(LLMError, match="timed out"):
        await provider.generate(request())
    await provider.aclose()


@respx.mock
async def test_ollama_turns_a_500_into_an_llm_error() -> None:
    respx.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(return_value=httpx.Response(500, text="boom"))
    provider = OllamaProvider(base_url=OLLAMA_URL)

    with pytest.raises(LLMError, match="500"):
        await provider.generate(request())
    await provider.aclose()


@respx.mock
async def test_ollama_rejects_an_empty_message() -> None:
    """A reply with no content is a failure, not an empty plan."""
    respx.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(return_value=chat_reply("   "))
    provider = OllamaProvider(base_url=OLLAMA_URL)

    with pytest.raises(LLMError, match="empty"):
        await provider.generate(request())
    await provider.aclose()


@respx.mock
async def test_ollama_stops_asking_for_no_thinking_once_refused() -> None:
    """Older daemons and non-reasoning models reject `think`.

    Requiring the user to know which they have would be a trap, so the first
    rejection turns the option off and the call is retried.
    """
    replies = [
        httpx.Response(400, text='{"error":"model does not support think"}'),
        chat_reply(an_intention()),
        chat_reply(an_intention()),
    ]
    route = respx.post(f"{OLLAMA_URL}{CHAT_PATH}").mock(side_effect=replies)
    provider = OllamaProvider(base_url=OLLAMA_URL)

    first = await provider.generate(request())
    assert first.ok, "the retry should have succeeded"
    assert '"think"' in route.calls[0].request.read().decode()
    assert '"think"' not in route.calls[1].request.read().decode()

    await provider.generate(request(agent_id=2))
    assert '"think"' not in route.calls[2].request.read().decode(), "it should not ask again"
    await provider.aclose()


@respx.mock
async def test_health_and_model_listing_survive_a_dead_daemon() -> None:
    respx.get(f"{OLLAMA_URL}{TAGS_PATH}").mock(side_effect=httpx.ConnectError("refused"))
    provider = OllamaProvider(base_url=OLLAMA_URL)

    assert await provider.healthy() is False
    assert await provider.models() == ()
    await provider.aclose()


@respx.mock
async def test_model_listing_reads_the_tags_endpoint() -> None:
    respx.get(f"{OLLAMA_URL}{TAGS_PATH}").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:8b"}, {"name": "x"}]})
    )
    provider = OllamaProvider(base_url=OLLAMA_URL)

    assert await provider.models() == ("qwen3:8b", "x")
    await provider.aclose()


# ----------------------------------------------------------------- scheduler


class CountingProvider:
    """A provider that records calls and can be told how to behave."""

    name = "counting"

    def __init__(self, fail: bool = False, delay_s: float = 0.0) -> None:
        self.calls = 0
        self.fail = fail
        self.delay_s = delay_s
        self.concurrent = 0
        self.max_concurrent = 0

    @property
    def model(self) -> str:
        return "counting-1"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if self.fail:
                msg = "provider said no"
                raise LLMError(msg)
            return LLMResponse(
                agent_id=request.agent_id,
                content=an_intention(),
                model=self.model,
                provider=self.name,
            )
        finally:
            self.concurrent -= 1

    async def healthy(self) -> bool:
        return not self.fail

    async def aclose(self) -> None:
        return None


def scheduler(provider: LLMProvider, **limits: object) -> LLMScheduler:
    """A scheduler with overridable limits."""
    return LLMScheduler(provider, SchedulerLimits(**limits))  # type: ignore[arg-type]


async def test_a_failure_comes_back_as_data_not_an_exception() -> None:
    """Every caller's response to a failure is the same: carry on."""
    provider = CountingProvider(fail=True)
    sched = scheduler(provider)

    response = await sched.submit(request())

    assert not response.ok
    assert response.error == "provider said no"


async def test_the_cache_saves_the_second_identical_call() -> None:
    provider = CountingProvider()
    sched = scheduler(provider, cache_size=8)

    first = await sched.submit(request(cache_key="abc"))
    second = await sched.submit(request(cache_key="abc"))

    assert provider.calls == 1, "the second call should have been served from cache"
    assert second.cached and not first.cached
    assert second.content == first.content


async def test_the_cache_is_bounded() -> None:
    provider = CountingProvider()
    sched = scheduler(provider, cache_size=2)

    for index in range(4):
        await sched.submit(request(cache_key=f"k{index}"))
    await sched.submit(request(cache_key="k0"))

    assert provider.calls == 5, "k0 should have been evicted"


async def test_calls_per_minute_is_enforced_without_blaming_the_provider() -> None:
    """Hitting our own limit must not count towards opening the circuit."""
    provider = CountingProvider()
    sched = scheduler(provider, max_calls_per_min=2)

    await sched.submit(request(agent_id=1))
    await sched.submit(request(agent_id=2))
    refused = await sched.submit(request(agent_id=3))

    assert provider.calls == 2
    assert refused.error == "rate limited"
    assert sched.breaker.consecutive_failures == 0


async def test_concurrency_is_capped() -> None:
    provider = CountingProvider(delay_s=0.02)
    sched = scheduler(provider, max_concurrency=2, max_calls_per_min=100)

    await asyncio.gather(*(sched.submit(request(agent_id=i)) for i in range(6)))

    assert provider.max_concurrent <= 2, f"ran {provider.max_concurrent} at once"


async def test_a_slow_provider_times_out() -> None:
    provider = CountingProvider(delay_s=0.5)
    sched = scheduler(provider, timeout_s=0.05)

    response = await sched.submit(request())

    assert not response.ok
    assert "timeout" in (response.error or "")
    assert sched.telemetry.stats.timeouts == 1


async def test_repeated_failures_open_the_circuit_and_stop_the_calls() -> None:
    provider = CountingProvider(fail=True)
    sched = LLMScheduler(
        provider,
        SchedulerLimits(max_calls_per_min=100),
        breaker=CircuitBreaker(threshold=3, cooldown_s=60.0),
    )

    for _ in range(3):
        await sched.submit(request(issued_sim_s=1.0))
    assert provider.calls == 3

    blocked = await sched.submit(request(issued_sim_s=2.0))

    assert blocked.error == "circuit open"
    assert provider.calls == 3, "an open circuit must not reach the provider"


async def test_the_circuit_closes_after_its_cooldown() -> None:
    provider = CountingProvider(fail=True)
    sched = LLMScheduler(
        provider,
        SchedulerLimits(max_calls_per_min=100),
        breaker=CircuitBreaker(threshold=1, cooldown_s=30.0),
    )
    await sched.submit(request(issued_sim_s=10.0))
    assert (await sched.submit(request(issued_sim_s=20.0))).error == "circuit open"

    provider.fail = False
    recovered = await sched.submit(request(issued_sim_s=45.0))

    assert recovered.ok, "the breaker should have closed after 30 sim-seconds"


async def test_telemetry_records_what_happened() -> None:
    sched = scheduler(CountingProvider(), cache_size=4)

    await sched.submit(request(cache_key="k"))
    await sched.submit(request(cache_key="k"))

    stats = sched.telemetry.stats
    assert stats.calls == 2
    assert stats.cache_hits == 1
    assert sched.telemetry.recent[0].cached is True


# ------------------------------------------------------------ speed policies


@pytest.mark.parametrize(
    ("policy", "speed", "expected"),
    [
        ("off", 25.0, None),
        ("reduced", 25.0, 80.0),
        ("full", 25.0, 20.0),
        ("off", 1.0, 20.0),
        ("reduced", 5.0, 20.0),
    ],
)
def test_high_speed_policy_decides_the_interval(
    policy: str, speed: float, expected: float | None
) -> None:
    """At speed, deliberation thins out rather than slowing the world down."""
    limits = SchedulerLimits(min_interval_sim_s=20.0, high_speed_policy=policy)  # type: ignore[arg-type]

    assert limits.interval_for_speed(speed) == expected


# ------------------------------------------------------------------- gateway


async def test_the_gateway_reports_a_mock_provider_honestly(settings: Settings) -> None:
    gateway = LLMGateway(settings, MockProvider())

    status = gateway.status()

    assert status.provider == "mock"
    assert status.model == "mock-deterministic"
    assert await gateway.check_health() is True


async def test_switching_provider_releases_the_old_transport(settings: Settings) -> None:
    """A swapped-out `AsyncClient` would otherwise leak its connection pool."""
    first = CountingProvider()
    closed: list[bool] = []

    async def record_close() -> None:
        closed.append(True)

    first.aclose = record_close  # type: ignore[method-assign]
    gateway = LLMGateway(settings, first)

    await gateway.switch("mock", "mock-deterministic")

    assert closed == [True]
    assert gateway.status().provider == "mock"


async def test_limits_can_be_changed_at_runtime(settings: Settings) -> None:
    gateway = LLMGateway(settings, MockProvider())

    gateway.set_limits(max_calls_per_min=7, max_agents=3)

    assert gateway.scheduler.limits.max_calls_per_min == 7
    assert gateway.status().max_agents == 3


async def test_disabling_is_immediate(settings: Settings) -> None:
    gateway = LLMGateway(settings, MockProvider())

    gateway.set_enabled(False)

    assert gateway.enabled is False
    assert gateway.status().enabled is False


async def test_refusals_are_counted_separately_from_failures() -> None:
    """Our own limits are not the provider's fault, but must still be visible.

    They were invisible at first, which made the monitor under-report: a live
    run showed 50 calls where twice that had been asked for.
    """
    provider = CountingProvider()
    sched = scheduler(provider, max_calls_per_min=1)

    await sched.submit(request(agent_id=1))
    await sched.submit(request(agent_id=2))
    await sched.submit(request(agent_id=3))

    stats = sched.telemetry.stats
    assert stats.calls == 1
    assert stats.refusals == 2
    assert stats.failures == 0, "a spent budget is not a provider failure"
    assert stats.failure_rate == 0.0
    assert stats.requested == 3, "everything asked for is accounted for"


async def test_a_refusal_appears_in_the_call_log_with_its_reason() -> None:
    sched = scheduler(CountingProvider(), max_calls_per_min=1)
    await sched.submit(request(agent_id=1))

    await sched.submit(request(agent_id=2))

    latest = sched.telemetry.recent[0]
    assert latest.ok is False
    assert latest.error == "rate limited"
    assert latest.latency_s == 0.0
