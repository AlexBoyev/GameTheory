# ADR 0002 - The simulation core

- **Status:** accepted
- **Date:** 2026-11-21
- **Context:** Phase 2 (survival loop and utility AI)

## Context

Phase 1 left a placeholder world behind a real API. Phase 2 had to put a
deterministic, performant survival simulation behind that same API without
changing anything above `SimulationService`, and without breaking the
determinism contract that makes experiments meaningful.

## Decisions

### 1. The tick pipeline is split across two layers

ADR 0001 fixed the direction of dependency: `ai/` reads `sim/`, never the
reverse. That decides where systems live:

| Layer | Systems |
| --- | --- |
| `sim/systems/` | `NeedsSystem`, `MovementSystem`, `RegrowthSystem`, `LifecycleSystem` |
| `ai/systems/` | `PerceptionSystem`, `DecisionSystem`, `SkillExecutionSystem` |

Both satisfy the same `sim.systems.System` protocol, so the engine cannot tell
them apart; `services/engine_factory.py` is the single place that knows about
both and fixes their order. The order is load-bearing - perception feeds the
decision, the decision starts a skill, the skill sets a velocity, movement
applies it - so it is an explicit list, never a discovered set.

### 2. Minds live outside the entity

`sim.entities.Agent` holds only what the world needs to simulate and draw it.
Memory, the decision trace and the running skill live in `ai.minds.Mind`,
indexed by agent id in a `MindRegistry` keyed on the world's `uid`. A reset
therefore cannot leak one world's memories into the next, and `sim/` stays
free of any reference to `ai/`.

### 3. Commands are acknowledged, not fired and forgotten

The engine runs on its own thread, so `POST /sim/step` would otherwise return
before its ticks had happened. `submit()` returns a sequence number, the
engine publishes `commands_applied` at the end of each slice (after any ticks
that command caused), and the service waits for it. That is what lets the REST
API keep its Phase 1 contract - step returns the tick the step produced.

### 4. Frames are generated on the engine thread, broadcast on the event loop

The engine pushes finished frames into a bounded queue of two and drops the
*old* frame when it is full: a client that falls behind should see the present,
not a backlog of the past. Resource amounts travel as deltas computed by the
service, which owns the broadcast cadence.

### 5. Performance came from measurement, not instinct

Two hypotheses about the hot path were wrong before profiling settled it.
`query_radius` was 30% of runtime, for two fixable reasons: the span formula
scanned 25 cells where 9 suffice (`ceil(radius / cell)`, not `int(...) + 1`),
and each candidate cost a dictionary lookup to fetch its position. Storing
`(id, x, z)` inline in the bucket and fixing the span, plus flattening the
terrain arrays into Python lists for scalar reads, bought roughly 65% at 500
agents. Numbers are in the README capacity table.

### 6. Water is a landmark, not a sighting

Perception is radius-limited at 18 units, which is the right model for a rabbit
or a rival: they move, so you only know about them when you can see them. A
lake does not move. `balance.LANDMARK_RADIUS` (54 units) applies to water
**only**, and models an animal knowing its own territory.

This is a deliberate refinement of SPEC 7.1. Without it, agents that spawned
inland died of thirst beside a lake they would obviously have known about.
Food is still found by sight, which is what keeps foraging - and later, telling
someone where the berries are - meaningful.

## The two balance bugs, and why `test_balance.py` exists

Every unit test passed while the default world killed 88% of its population by
tick 9000. Both causes were invisible to any single-system test:

1. **Permanent panic.** Safety drained at 14/sim-s while recovering at
   0.6/sim-s, so on a crowded island every agent's safety sat at zero and
   `Flee` outscored `Drink`. Agents fled until they died of thirst. Fixed by
   pairing the two rates (7 against 3.5), making threats rarer and closer
   (aggression 0.8, radius 5), and making fear yield to a lethal need - a
   dying agent stops caring about a glowering neighbour.
2. **Unreachable water.** Drinking spots were placed in water-edge *water*
   cells, but movement refuses to walk into the sea. Agents approached the
   bank, never got within arrival distance, and drank forever without
   drinking - 86 of 120 were running `Drink` as they died. Fixed by placing
   spots on the dry side of the shoreline (`shore_cells`).

`tests/sim/test_balance.py` runs a real population for 6,000 ticks and insists
most of them live, with a named cause when they do not. It is the only test in
the suite that would have caught either bug, and it is the reason the invariant
"this world is survivable" is now machine-checked rather than assumed.

## Consequences

- Survival across seeds is 92-99% over 6,000-12,000 ticks, with occasional
  starvation as the remaining pressure - which is the intended kind.
- The engine is deterministic to the bit for a given seed, verified over 1,000
  ticks of the full pipeline.
- Phase 4 can add encounter systems to the same pipeline without touching the
  transport, the stores or the renderer.
