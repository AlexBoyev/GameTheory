# ADR 0001 - Overall architecture

- **Status:** accepted
- **Date:** 2026-11-21
- **Context:** Phase 1 (scaffold)

## Context

Game Theory runs an autonomous society simulation on localhost and streams it
to a browser. Three forces shape the architecture:

1. **Determinism is a feature.** "Same seed, LLM off, identical world after N
   ticks" is how we tell a strategy actually won from a lucky run. Anything
   that can perturb the number stream - wall clock, global RNG, iteration over
   an unordered set - is a correctness bug, not a style issue.
2. **The simulation must never wait for an LLM.** A local 8B model answers in
   seconds; a tick is 100 ms. The deliberative layer has to be asynchronous and
   droppable, and the world has to stay fully playable with no model installed.
3. **It must cost nothing.** No cloud AI, no API keys, no billing.

## Decisions

### 1. Layered backend, enforced by a linter

`api -> services -> persistence -> ai -> sim`, checked by import-linter on every
run (`uv run lint-imports`). Seven contracts, including:

- `sim/` cannot import FastAPI, httpx, SQLModel, `ai.llm`, **or `time`,
  `datetime`, `random`, `uuid`** - determinism is machine-checked, not trusted.
- `ai/llm/` cannot import `sim/` at all; it receives DTOs.
- `api/` cannot name a `sim`/`ai`/`persistence` module directly.

A linted contract is worth more than the same rule written in a document,
because it fails in CI rather than in review.

### 2. Tightening SPEC 2.1: `sim/` does not import `ai/`

SPEC 2.1 allows `sim/ -> ai/ interfaces` while also allowing `ai/ -> sim/ read
models`. Both at once is a cycle, and a cycle cannot be expressed as layers.
We chose the direction that holds everywhere else in the design: **`ai/` reads
`sim/`, never the reverse.** The Phase 2 decision system therefore lives in
`ai/` (or receives injected `Brain` objects) rather than inside `sim.systems`.

### 3. Wall-clock access is injected, not imported

The engine needs real time to pace ticks, but `sim/` may not import `time`.
`sim.engine.Pacer` is a protocol; `services.pacer.MonotonicPacer` is the only
implementation that touches the clock, and `FrozenPacer` makes engine tests
instant and deterministic.

### 4. Services produce envelopes; the transport serialises them

`services/` builds plain `Envelope(type, tick, data)` objects and knows nothing
about WebSockets. `api/ws/hub.py` fans them out through a `Serializer`
protocol (JSON now, msgpack later). The hub subscribes to the service, so a
dead socket can never break the broadcast loop and the layering holds.

### 5. One composition root

`app/container.py` wires every service once; `app/main.py` builds it in the app
factory and stores it on `app.state`. No module-level singletons, no service
locator, and tests construct their own container with their own settings.

### 6. `WorldConfig` lives in `core/`

Both `sim/` (which consumes it) and `api/` (which exposes it verbatim as a DTO)
need the world configuration schema. Putting it in the layer-free `core/`
package avoids duplicating the schema or breaking the layering to share it.

### 7. Mock-first LLM

`MockProvider` is the default, is deterministic, and is the automatic fallback
when Ollama is unreachable. The circuit breaker counts cooldown in
**sim-seconds**, not wall-clock seconds, so it behaves the same at 1x and 50x.

### 8. The frontend owns no backend address

Vite proxies `/api` and `/ws`; nginx does the same in production. REST types
are generated from the OpenAPI schema (`npm run gen:api`), never hand-written -
with an offline path (`uv run python -m app.tools.dump_openapi`) for cold
checkouts and CI. The WS envelope types are hand-written, since the WS protocol
is not part of OpenAPI.

### 9. Frames are interpolated, not trusted as positions

The backend broadcasts at most 20 Hz; the renderer runs at 60. `previous` and
`current` frames are kept and interpolated, with the factor **clamped** - a
late frame holds the last pose instead of extrapolating agents into the sea.

## Consequences

- Adding a feature that breaks the layering fails `lint-imports` immediately.
- Phase 2 can replace the Phase 1 placeholder world without touching `api/`,
  the stores, or the renderer: `SimulationService` keeps its interface.
- Determinism survives refactors, because the rules that protect it are tests
  and contracts rather than conventions.
