# ADR 0004 - LLM minds without ever waiting for one

- **Status:** accepted
- **Date:** 2026-11-21
- **Context:** Phase 5 (the deliberative layer, local Ollama or an offline mock)

## Context

Phases 2-4 produced agents that react well: utility AI picks the best action
for the moment, game theory decides how they treat each other. What they
cannot do is *scheme* - hold a goal across minutes, say why, or change their
mind about a person.

A language model can do that, and brings three problems with it. It is slow
(hundreds of milliseconds at best, on a local model), it is optional (most
people will not have Ollama installed), and it is unreliable (timeouts, prose
instead of JSON, a daemon that is not running). CLAUDE.md rule 3 is therefore
absolute: **the simulation never awaits an LLM call.**

## Decisions

### 1. A two-way mailbox between the engine thread and the event loop

The engine runs on a worker thread; everything async runs on the event loop.
`ai/llm/broker.py` is the only thing both touch:

| Thread | Calls |
| --- | --- |
| Engine (`IntentionSystem`) | `post` a snapshot, `collect` whatever came back |
| Event loop (`LLMPump`) | `take_pending`, then `deliver` |

Both sides are non-blocking, so the worst case for the simulation is that no
plans arrive. A deliberative agent with no plan is just a utility-AI agent.

The pending queue is a bounded `deque`, and when it overflows the **oldest**
request is dropped: an intention formed from a situation thirty seconds stale
is worse than no intention at all.

### 2. Nothing that crosses the boundary is a live object

`ai/prompting.py` turns an agent into a `PromptContext` of plain strings and
numbers on the engine thread. By the time a reply arrives the world has moved
on - the agent may have died, or the world may have been reset - so holding a
reference to an `Agent`, a `World` or a `Mind` would be a bug waiting to
happen. Every delivery is also stamped with `world.uid`, and a reply whose
stamp does not match the current world is discarded rather than applied to a
world it was not thinking about.

This also keeps the import-linter contract *"ai/llm/ receives DTOs, never sim
internals"* true: the `PromptContext` dataclass lives in `ai/llm/`, but the
code that reads the world to build one lives a layer up in `ai/`.

### 3. A plan biases the choice; it never overrides it

A returned `Intention` adds `INTENTION_BONUS = 0.35` to the utility score of
the skills it names, for `INTENTION_LIFETIME_SIM_S = 45` sim-seconds. It does
not select an action.

That is what makes the whole layer safe. A starving schemer still eats first,
because hunger scores higher than any bias; an expired plan simply stops
counting; switching the provider off mid-run changes nothing except that
nobody has a thought. There is a test for each of those.

### 4. Every limit lives in the scheduler, and failures are data

`LLMScheduler.submit` never raises and never blocks longer than its timeout.
It owns the LRU cache, the calls-per-minute budget, the concurrency gate, the
timeout and the circuit breaker, and returns an `LLMResponse` carrying
`error` when it cannot help - because every caller's correct response to a
failure is identical: carry on with utility AI.

Refusals (a spent budget, an open circuit) are counted **separately** from
failures. They were originally invisible, which made the monitor under-report
badly: a live run showed 50 calls where twice that had been asked for, with
nothing on screen to explain the gap. A refusal is our own limit working, not
the provider's fault, so it must not inflate the failure rate either.

### 5. The high-speed policy is applied by the service, not the engine

Deliberation is the one part of a tick whose cost the simulation does not
control, so above `high_speed_threshold` it either thins out (`reduced`:
four times the interval) or stops (`off`). Deciding that needs the engine's
current speed *and* the runtime-configurable limits, which only the service
layer has - so `SimulationService` pushes an interval into the broker on
every broadcast, and `IntentionSystem` reads it.

Worth recording because the first cut had `interval_for_speed` as a tested,
documented, API-settable function that **nothing ever called**: the setting
existed, the UI displayed it, and it did nothing. A live probe at 10x is what
exposed it - the call budget was being spent five times faster than the
policy was supposed to allow.

### 6. Prose instead of JSON gets exactly one repair attempt

Ollama is asked for constrained decoding (`format` = the `Intention` JSON
schema), so valid output is the normal case. When it is not, the pump strips
the code fences models like to add, and failing that re-asks once with a note
saying the reply was not valid JSON. A model that cannot produce its own
schema twice will not manage it on the third attempt, and the agent has
utility AI to fall back on.

`think: false` is sent only until a daemon objects to it, after which the
provider stops asking for the life of the process. Requiring the user to know
whether their model is a reasoning model would be a trap.

### 7. Reflection is triggered by a life, not a timer

Reflection reads an agent's history rather than its moment, so it is the
expensive call. It fires after `REFLECT_EVERY_IMPORTANT = 8` *important*
events (importance >= 5) happen to one agent, counted by `AgentMemory`
because its episodic buffer is bounded and its length says nothing about how
eventful a life has been. An agent nothing happens to never pays for one.

Beliefs land in `AgentMemory.beliefs`, which already existed, rather than in a
second list on the `Mind`.

## Consequences

- **Nothing needs installing.** `MockProvider` is the default and builds a
  deterministic plan from a hash of the prompt, so the deliberative layer is
  visible and testable with no model present. Four agents deliberate by
  default (`WorldConfig.llm_agents`), which is why haloes, speech bubbles and
  thoughts appear out of the box.
- **Determinism is conditional, as the SPEC always said.** Same seed with the
  LLM off is still bit-for-bit reproducible; with it on, replies arrive on the
  event loop and no seed controls that timing. `llm_agents = 0` restores it.
- The provider is swapped through `LLMGateway.switch(name, model)` rather than
  by handing the router a provider, so `api/` keeps its contract of never
  importing `ai/`. The old transport is closed on the way out - a dropped
  `AsyncClient` leaks a connection pool for the life of the process.
- Every test runs against `MockProvider` or an respx-faked daemon: success,
  timeout, HTTP 500, empty message, unparseable reply, a rejected `think`,
  rate limiting, concurrency capping and the breaker opening and closing.
