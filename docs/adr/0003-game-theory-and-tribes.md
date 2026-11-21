# ADR 0003 - Game theory, manipulation and tribes

- **Status:** accepted
- **Date:** 2026-11-21
- **Context:** Phase 4 (encounters, social memory, tribes, reproduction, metrics)

## Context

Phase 2 produced a world where 120 agents survive competently and ignore each
other. Phase 4 had to make them a *society*: pairwise games with real payoffs,
beliefs about each other that can be wrong, groups that form and fall apart,
and numbers that say what happened - without touching the determinism contract
or letting `sim/` learn about `ai/`.

## Decisions

### 1. Encounters are a system, not a skill

A game needs two agents to act at once, and a skill only ever runs for one.
`ai/systems/encounter_system.py` therefore pairs up agents who are close
enough, asks `EncounterResolver` which game their situation implies, and
applies the result to both. Skills remain strictly single-agent, which keeps
`check`/`start`/`step` honest and testable.

Which game gets played is a function of the world, not a die roll:

| Situation | Game |
| --- | --- |
| A deer nearby that one agent cannot bring down | Stag Hunt |
| Both want the same resource node | Hawk-Dove |
| Otherwise, two agents meeting | Prisoner's Dilemma |
| A trade proposal | Ultimatum |
| Tribe storage, each season | Public Goods |

Payoffs come from `config/payoffs.yaml` (T > R > P > S is validated on load),
and trembling-hand noise means an agent's intention and its action can differ -
which is what makes forgiving strategies worth anything.

### 2. Food is transferred, never created

Every payoff is applied as a transfer between the two agents or between an
agent and the world. A cooperation payoff that *added* food would make
cooperation an infinite food source and the whole economy meaningless; the
resolver has no path that mints food.

### 3. Trust is first-hand; reputation is hearsay

`Relationship.trust` only ever moves from something an agent personally
experienced. What it hears from others lands in a separate reputation belief,
and `social.effective_opinion` blends the two with first-hand evidence
dominating. This is the whole substrate for manipulation:

- Gossip is weighted by how much the listener trusts the teller:
  `credence = (trust + 1) / 2`, scaled by `GOSSIP_WEIGHT = 0.35`. A liar
  nobody trusts changes nothing.
- A lie can be caught, and the chance rises when it contradicts what the
  listener saw for themselves. Being caught costs the liar trust with everyone
  present - so dishonesty is profitable only while it is believed.

### 4. Tribes emerge from the trust graph

A tribe is founded by an agent (`FoundTribe`) and joined by agents who already
trust a member - it is never assigned. Leadership is held by legitimacy
(`reputation x charisma x tenure`, where reputation is literally the average
trust the members hold in that agent), so a leader the tribe sours on becomes
vulnerable to `ChallengeLeader` without any special-case code.

`ChallengeLeader` requires a clear margin (`COUP_MARGIN = 0.25`) rather than a
bare majority, which is why most challenges fail. That made the first version
of the metrics misleading: the ledger counted only *successful* coups while the
`coup` event fired for attempts too, so the charts read `coups: 0` in a world
that had plotted ten times. The ledger now counts `coups` and `coup_attempts`
separately and the metric exposes both as `coups_won` / `coups_tried`.

### 5. Metrics are sampled by elapsed ticks, not by divisibility

Sampling runs on the broadcast thread so the engine never pays for it. That
means the sampler is only ever *asked* on the ticks that happen to land on a
20 Hz frame - and at 25x those are about twelve ticks apart. The first
implementation sampled when `tick % 100 == 0`, which almost never coincided
with a frame: a 6,244-tick run produced **one** data point, whose `extra`
reported zero tribes and zero shelters because it was taken before either
existed, and the charts panel stayed empty exactly when the world got
interesting.

`MetricsService.is_due(tick, last_sampled)` asks whether the interval has
*elapsed*, and the service books the tick it actually recorded rather than the
frame tick that triggered it (the world advances while the frame is in flight,
which otherwise let the recorded spacing drift to 82 ticks on a nominal 100).
A regression test simulates 20 Hz frames over a 250 tick/s world.

### 6. `uvicorn --reload` is not used; the driver reloads instead

On this Windows host, `uvicorn --reload` announces `Reloading...` and never
finishes: the worker process keeps running and keeps serving. The failure mode
is the dangerous kind - the server stays healthy while answering with code you
have already changed, so an edit appears to have no effect and the obvious
conclusion ("my fix didn't work") is wrong. Reproduced deterministically at
default speed with nothing but a touched file.

`driver.py` therefore runs uvicorn plainly, watches `backend/app` and
`backend/config` for `.py`/`.yaml` changes, and restarts the whole child
process on change (debounced, with a tree kill it already does reliably), then
waits for `/api/health` before saying `backend reloaded`. `--no-reload` turns
it off. The driver's output pump was also made encoding-proof: Vite's `➜`
crashed the pump thread on this console's cp1255 code page, silently killing
the log stream while the servers kept running.

## Consequences

- An LLM is not required for any of this. `ai/gametheory/` is pure policy over
  numbers, so the whole society runs deterministically with the LLM off, and
  the `LLM` strategy is one strategy among ten rather than a dependency.
- Social state lives in `MindRegistry` and `SocialLedger`, both outside the
  world, so the determinism and reset guarantees from ADR 0002 are unchanged.
- The ledger is global aggregate state. It is owned by the service layer and
  passed in, never reached for, so a reset clears it in one place.
- Tribe skills were the one Phase 4 category with no direct tests when the
  phase was otherwise complete; `tests/ai/test_tribes.py` now covers founding,
  joining, leaving, the common store, coups and diplomacy (27 tests), which is
  what caught the coup accounting.
