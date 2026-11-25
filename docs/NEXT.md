# What is left, in the order I would do it

Written 2026-11-23, updated 2026-11-25, so a fresh session can pick up
without re-deriving the state. `docs/REVIEW.md` has the reasoning behind each
finding; this is the queue. Everything here was checked against the code.

**Start here:** the repo is `F:\Projects\GameTheory`, published at
https://github.com/AlexBoyev/GameTheory. One command runs everything:
`python driver.py` (app), `python driver.py --check` (all nine checks),
`python driver.py --bench`.

Recent, from using it rather than reading it: the engine froze outright at
25x/50x, the world ran before Start, every preset silently overrode the
population slider, and the two data-backed overlays drew nothing without
saying so. Then a second round, all from one complaint ("too slow, and what
am I even watching"):

- **The loop slept 62% of the time**, at every speed including MAX, so the
  published throughput ceiling was never what you got. Fixed; MAX is now
  2.7-3x faster and sits at the raw pipeline's own rate.
- **A step bigger than one slice froze the UI** - the same unbudgeted-batch
  bug, in the one code path that had never been given a budget. Fixed; skips
  are chunked, report progress, and Pause cancels them.
- **Two thirds of gathering trips failed** because somebody emptied the node
  during the walk, and the agent gave up rather than walking on. Fixed; it
  costs nothing and pays twice (fewer decisions, more competent agents).
- **A day passed with nothing to mark it.** Fixed: a title card per day, kept
  in the log so a day you looked away for is still there.

## 0. The open question: the island is below replacement

Chased all the way down on 2026-11-25 and left deliberately unfixed,
because the fix is a judgement about what this simulation should be and
that is not mine to make silently.

Everybody starts adult (18-50) and ages three years a sim-day, so the
oldest founder dies on day 7.3 and the youngest on day 18: the entire
founding cast is gone by day 18. About 86 children arrive to replace 120
adults, so the island is below replacement, and whether one is still
inhabited at day 30 is chance - three seeds ended at 215, 16 and 5 with
identical settings.

The funnel, measured on well-fed adults of breeding age: 39% have somebody
of breeding age within reach, 26% have met them before, 4.4% trust each
other at 0.20, 2.1% at the default 0.35. Half of all `Reproduce` refusals
are "not well fed enough" and 70% of those are agents who are not hungry
at all but carry less than the two units of food the check wants. When a
child is possible the brain chooses it half the time, so utility is not
the bottleneck.

None of that is a bug: cooperating is +0.12 trust and defecting -0.22, and
most pairs never meet twice. It is the trust model's own consequence. The
levers, in the order I would try them:

1. `reproduction_min_trust` (now world config, default unchanged at 0.35,
   with a dial). 0.20 roughly doubles the share of adults with a partner
   at hand. **Measure the day-30 spread over three seeds before changing
   the default.**
2. `Reproduce.MIN_FOOD` (2.0 against a median carried 0.27). The belly
   gate never binds; this one does.
3. `age_years_per_day` (3.0). Slower ageing buys more fertile days, at the
   cost of the thing the number was chosen for - a watchable lifetime.

**The rule this produced:** past about day 10, three seeds is the minimum
and the spread *is* the result. A single-seed run of this world will
support any conclusion you like.

## 1. The other honest lever: the cost of a tick

Now that the loop gives up nothing, speed is purely the cost of a tick, and
that is dominated by one thing. Profiled at 300 agents: `query_radius` is 32%
of self time and 45% cumulative, driven by `check()` and `considerations()`
calls that each ask a spatial question. ADR 0005 records that per-tick
memoisation of `nearest_resource` was tried and reverted (~4% for real
staleness risk), so the lever is not caching the answers but *asking fewer
questions* - the `Requirement` prefilter is the shape of the thing that
worked before, and nothing yet prefilters on distance.

## 2. Things that look like gaps and are not

Do not "fix" these; each was checked and is deliberate.

- `ResourceKind.STONE` spawns and is consumed by nothing. Scenery; the help
  overlay says so rather than promising a use.
- `EventType.ENCOUNTER` never reaches the feed. It is the *memory* entry for
  an encounter; the feed gets `BETRAYAL`/`COOPERATION`/`COMBAT`/`DEFECTION`.
- `EventType.LEADER_CHANGED` fires only when a leader dies. A won coup emits
  `COUP` with `succeeded: true`.
- `AgentState.MOVE` is plan-only. `AgentState.TRADE` does happen; it is just
  too brief to catch with coarse sampling.
- `WorldConfig.strategy_mix` is read through `normalised_strategy_mix`.
- Every REST endpoint in the OpenAPI schema is called by the frontend; the
  `metrics` websocket envelope is not, deliberately - the charts poll REST
  instead, which `simStore` says in a comment. (The `agent_detail` envelope
  used to be in the same position and was retired; see `docs/REVIEW.md`.)
- `ui/primitives.tsx` is a module of shared pieces (Panel, Meter, Row), not
  a component, so "never rendered" searches flag it wrongly.
- `llm_agents` defaults to 4, so default runs are not bit-reproducible.
  Deliberate, documented in ADR 0004 and `docs/REVIEW.md`.

## 3. Still needs Alex, not Claude

- **Deal with `F:\Projects\TheoryGames`.** Left by the rename, and *not* quite
  empty: it still holds a `.idea` folder, so deleting it throws away that
  PyCharm project's settings rather than nothing. Your call whether those
  matter. A session's working directory was pinned inside it, which is why git
  reported "not a repository" from there; start Claude Code in
  `F:\Projects\GameTheory`.

---

## How to look for the next real bug

Seven things in this project have been declared, typed, unit-tested, and
connected to nothing: `Raid`, a winnable coup, tribe pacts, three of the four
database tables, two circuit-breaker settings, and a tick-rate setting that
described behaviour it did not control. None were found by reading code or by
running the suite. They were found two ways, both worth repeating.

**Run a world and ask what happened.** `tests/ai/test_reachability.py` keeps
that instrument pointed at the skills. Read its docstring before changing it:
both of its sharp edges (read each skill's score, not the decision trace,
which keeps only the top three; and sample every tick, because every 25th
missed `OfferPeace` in a seed that demonstrably made peace) cost a wrong
answer before they were written down.

The third pass to run, when the first two go quiet, is over the **protocol**
rather than the code: every endpoint in `frontend/openapi.json` against the
frontend's calls, every websocket envelope type against its handlers, and
every field a message sets against whatever reads it. That is what turned up
`subscribed_agent` above.

**Sweep declarations for readers.** For every field, constant and enum
member, count references outside its own file. Three of the seven fell out of
one pass over `Settings`, `WorldConfig`, `balance` and the DTOs. Two traps:
a name read through a property (`strategy_mix` via `normalised_strategy_mix`)
is a false positive, and a default duplicated at the use site
(`CircuitBreaker(threshold=3)` matching `llm_circuit_failures: int = 3`) is
how a missing wire hides from exactly this kind of search - the behaviour
looks right because the numbers agree by coincidence.

A guard test for the `Settings` half of that sweep is worth having and is not
written: an attempt behaved inconsistently between pytest and a plain
interpreter on identical inputs, and chasing it was not a good use of the
time. Whoever picks it up should reproduce the discrepancy first rather than
trusting either result.
