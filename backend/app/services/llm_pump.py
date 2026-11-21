"""The only place in the app that waits for a language model.

The engine thread posts snapshots into an `IntentionBroker` and carries on
ticking. This pump, on the event loop, renders them into prompts, sends them
through the scheduler (which owns every limit), parses what comes back, and
hands the result to the broker for the engine to collect.

Nothing here can slow the simulation down: if the model is unreachable or
hopeless, requests fail, agents keep running on utility AI, and the only
symptom is that nobody has a thought.
"""

import asyncio
from contextlib import suppress
from hashlib import blake2s

import structlog
from pydantic import ValidationError

from app.ai.llm.broker import Delivery, IntentionBroker, PendingRequest
from app.ai.llm.gateway import LLMGateway
from app.ai.llm.prompt_builder import PromptBuilder, estimate_tokens
from app.ai.llm.schemas import Intention, LLMRequest, Reflection

LOG = structlog.get_logger(__name__)

IDLE_SLEEP_S = 0.25
"""How long to wait when there is nothing to deliberate about."""

BATCH = 4
"""How many snapshots to take off the broker at once."""

PREVIEW = 2000
"""How much of a prompt and reply to keep for the inspector."""

SYSTEM_PROMPT = (
    "You are one person in a survival simulation. Decide what to do next, in "
    "character, using only the actions listed. Reply with JSON only."
)

REPAIR_NOTE = (
    "\n\nYour previous reply was not valid JSON for the schema. "
    "Reply again with JSON only, no prose, no code fences."
)


def cache_key(prompt: str, model: str) -> str:
    """A short, stable key for the prompt cache.

    The agent id is already part of the prompt (its name, needs and
    relationships are), so identical situations share an answer - which is
    what makes the cache worth having at 25x.
    """
    digest = blake2s(f"{model}\n{prompt}".encode(), digest_size=12)
    return digest.hexdigest()


class LLMPump:
    """Drains the broker, calls the model, delivers the results."""

    __slots__ = ("_broker", "_builder", "_gateway", "_task", "batch", "idle_sleep_s")

    def __init__(
        self,
        broker: IntentionBroker,
        gateway: LLMGateway,
        builder: PromptBuilder | None = None,
        idle_sleep_s: float = IDLE_SLEEP_S,
        batch: int = BATCH,
    ) -> None:
        self._broker = broker
        self._gateway = gateway
        self._builder = builder or PromptBuilder()
        self._task: asyncio.Task[None] | None = None
        self.idle_sleep_s = idle_sleep_s
        self.batch = batch

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Run the pump as a background task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="llm-pump")

    async def stop(self) -> None:
        """Cancel the pump and wait for it to finish."""
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    @property
    def running(self) -> bool:
        """Whether the background task is alive."""
        return self._task is not None and not self._task.done()

    # ----------------------------------------------------------------- loop

    async def run(self) -> None:
        """Deliberate forever, one batch at a time."""
        while True:
            if not self._gateway.enabled:
                await asyncio.sleep(self.idle_sleep_s)
                continue

            pending = self._broker.take_pending(self.batch)
            if not pending:
                await asyncio.sleep(self.idle_sleep_s)
                continue

            # Gathered rather than sequential: the scheduler's semaphore is
            # what limits real concurrency, so this just stops one slow call
            # from holding up the others in the same batch.
            await asyncio.gather(*(self._handle(item) for item in pending))

    async def _handle(self, pending: PendingRequest) -> None:
        """Deliberate for one agent, delivering whatever the result is."""
        agent_id = pending.context.agent_id
        try:
            delivery = await self._deliberate(pending)
        except asyncio.CancelledError:
            # Put the agent back in play; it will be asked again later.
            self._broker.deliver(Delivery(agent_id=agent_id, world_uid=pending.world_uid))
            raise
        except Exception as failure:  # one bad reply must not stop the pump
            LOG.warning("llm.pump_error", agent_id=agent_id, error=str(failure))
            delivery = Delivery(agent_id=agent_id, world_uid=pending.world_uid, error=str(failure))
        self._broker.deliver(delivery)

    async def _deliberate(self, pending: PendingRequest) -> Delivery:
        """Build the prompt, call the model, parse the answer."""
        reflection = pending.context.kind == "reflection"
        schema = Reflection if reflection else Intention
        prompt = (
            self._builder.build_reflection_prompt(pending.context.context)
            if reflection
            else self._builder.build_intention_prompt(pending.context.context)
        )
        if self._builder.over_budget(prompt):
            LOG.info(
                "llm.prompt_over_budget",
                agent_id=pending.context.agent_id,
                tokens=estimate_tokens(prompt),
            )

        scheduler = self._gateway.scheduler
        request = LLMRequest(
            agent_id=pending.context.agent_id,
            kind=pending.context.kind,
            system=SYSTEM_PROMPT,
            prompt=prompt,
            json_schema=schema.model_json_schema(),
            issued_sim_s=pending.issued_sim_s,
            cache_key=cache_key(prompt, scheduler.provider.model),
        )

        response = await scheduler.submit(request)
        if not response.ok:
            return Delivery(
                agent_id=request.agent_id,
                world_uid=pending.world_uid,
                error=response.error or "no content",
                prompt=prompt[:PREVIEW],
            )

        parsed = self._parse(response.content, reflection=reflection)
        if parsed is None:
            # One repair attempt, then give up: a model that cannot produce
            # its own schema twice will not manage it on the third try, and
            # the agent has utility AI to fall back on.
            repair = request.model_copy(
                update={"prompt": request.prompt + REPAIR_NOTE, "cache_key": ""}
            )
            response = await scheduler.submit(repair)
            parsed = self._parse(response.content, reflection=reflection) if response.ok else None

        sent, got = prompt[:PREVIEW], response.content[:PREVIEW]
        if parsed is None:
            return Delivery(
                agent_id=request.agent_id,
                world_uid=pending.world_uid,
                error="unparseable reply",
                prompt=sent,
                response=got,
            )
        if isinstance(parsed, Reflection):
            return Delivery(
                agent_id=request.agent_id,
                world_uid=pending.world_uid,
                reflection=parsed,
                prompt=sent,
                response=got,
            )
        return Delivery(
            agent_id=request.agent_id,
            world_uid=pending.world_uid,
            intention=parsed,
            prompt=sent,
            response=got,
        )

    @staticmethod
    def _parse(content: str, *, reflection: bool) -> Intention | Reflection | None:
        """Parse a reply, tolerating the code fences models like to add."""
        text = content.strip()
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        model = Reflection if reflection else Intention
        try:
            return model.model_validate_json(text)
        except ValidationError:
            return None
