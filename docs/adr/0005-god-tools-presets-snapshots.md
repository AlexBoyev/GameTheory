# ADR 0005 - God tools, presets, snapshots, and one rejected optimisation

- **Status:** accepted
- **Date:** 2026-11-22
- **Context:** Phase 6 (operator tools, named worlds, persistence, performance)

## Context

Phases 2-5 built a world that runs itself. Phase 6 is about the person
watching it: being able to *ask a question* of the simulation (what happens to
a cooperative island in a drought?), save the answer, and come back to it.

## Decisions

### 1. Interventions are an engine command, not an API that reaches into the world

A god tool mutates a live world that a worker thread is ticking. Rather than
locking from the outside, `sim.engine.Intervene` carries a callable the engine
runs between ticks under its own lock. The engine knows *when* it is safe to
apply something; the service layer knows *what* dropping food means.

Two bugs came out of writing them, both caught by tests:

- `World.living_agents()` is cached per tick and its docstring says anything
  adding or removing an agent must call `invalidate_living()`. Spawning and
  smiting did not, so a spawned agent was invisible to every system and to the
  API until the next tick, and the dead kept walking.
- Events were only drained from the world inside `_tick`, so an intervention
  on a **paused** world never reached the feed. A world that silently changes
  under you makes the feed a liar, so `_maybe_emit` now drains regardless.

### 2. A preset is overrides on `WorldConfig`, not a parallel schema

`config/presets/*.yaml` carry nothing but `WorldConfig` fields, validated
against it at load time. So a preset can only ever say something the config
can already express, a typo is a loud error rather than a setting that
silently does nothing, and "Tribal Wars, but 300 agents" is one request
(`POST /sim/reset` takes a preset *and* a config, applying one over the
other). The seed is never overridden - choosing a preset must not throw away
a seed typed in beside it.

Two fields existed in `WorldConfig` but did nothing until the presets needed
them: `trait_bias` (Liars' Island is low honesty and high cunning) and
`initial_tribes` (Tribal Wars starts with four tribes already formed, grouped
by where they spawned so their territory overlaps and the wars have a cause).
`trait_bias` moves the *mean* of a trait by solving the beta parameters for
it, so a dishonest island still contains the occasional honest agent - which
is the interesting case, and would be lost by clamping.

### 3. A snapshot stores the society, not the scenery

Terrain is a pure function of the config and the seed, so it is regenerated on
load rather than stored - which is the difference between tens of kilobytes
and megabytes. Minds **are** stored: a world reloaded without its memories
looks identical for one tick and then behaves like a world of strangers, and
the society is the interesting state.

Restoring exposed a third bug of the same family: `MindRegistry
.on_world_replaced` cleared every mind unconditionally, and the engine
announces a world replacement after a load - so the restored memories were
wiped a moment after being read. It is now guarded on the world uid: a world
it has already adopted is not a *different* world.

Two storage-layer defects surfaced too. `SnapshotRecord` was read after its
session closed (`DetachedInstanceError`), fixed by reading the values before
the insert and by setting `expire_on_commit=False` - every repository method
hands rows to a caller outside the session scope, so the SQLAlchemy default
made reading any of them a landmine.

`SocialLedger.clear()` listed every field by hand, which is how
`coup_attempts` came to leak between worlds in Phase 4. `clear`, `to_dict` and
`load` are now derived from the dataclass fields, so adding a counter cannot
forget any of them.

RNG streams are re-derived from the seed on load rather than restored, so a
loaded world is deterministic *going forward* but not bit-identical to the run
it came from. That is a deliberate trade, and it is written down rather than
implied.

### 4. The performance pass: profiled, optimised, measured, reverted

Phase 6 asked for a profile at 500 agents and a fix for the top issue. The
profile is unambiguous about where the time goes:

| | calls / 400 ticks | self time |
| --- | --- | --- |
| `SpatialHash.query_radius` | 495,097 | 26% |
| `UtilityBrain._score_all` (cumulative) | 13,983 | 44% |

The brain scores all 31 skills per decision, and each skill's `check()` and
`utility()` runs its own neighbour search. Instrumenting the calls showed
**32% of them are the same question asked two or three times in one tick**,
so the obvious fix was a per-tick memo on the world.

It was implemented, and then reverted. Two reasons, in order:

1. **It is not safe.** The premise - "nothing can change between these calls
   within a tick" - is false. Skills mutate the world *during* a tick: one
   depletes the node another just looked up. Three existing tests failed
   immediately, which is the good case; at runtime it would have produced
   slightly wrong decisions and no error at all.
2. **It did not pay.** An A/B in one process, with no profiler distorting it,
   measured 52.1 vs 49.8 ticks/s - about 4%, with the memoised runs ranging
   48.5-55.1 and overlapping the baseline. cProfile had over-weighted a
   function called half a million times in short bursts.

So the hot path is now *understood* and documented, and the code is unchanged.
A 4% gain inside the noise is not worth a staleness hazard nothing would
notice. The real headroom is structural - not scoring 31 skills when an
agent's situation rules most of them out - and that is a larger change than a
performance pass should smuggle in.

The one performance change that did land this phase came from a correctness
fix, not an optimisation: ADR 0004's spatial-hash bounding-box repair is both
correct and ~20% faster at 500+ agents, because the exact box is often 2x2
cells where the old span was always at least 3x3.

## Consequences

- Every endpoint in the SPEC is now implemented; nothing answers 501. The test
  that used to assert "snapshots announce Phase 6" now asserts the opposite
  for every endpoint, so a future placeholder is caught.
- `tribe_identity` (names, palette) moved from `ai/skills/tribe.py` into
  `sim/`, because world generation needs to name the tribes a preset starts
  with and `sim/` may not import `ai/`.
- The minimap, screenshot button and god panel are all read-only views or thin
  wrappers over the API, so none of them can desynchronise from the world.
- Bench, full Phase 6 pipeline: 283 ticks/s at 100 agents, 50 at 500, 22 at
  1,000.
