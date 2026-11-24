# What is left, in the order I would do it

Written 2026-11-23, updated 2026-11-24, so a fresh session can pick up
without re-deriving the state. `docs/REVIEW.md` has the reasoning behind each
finding; this is the queue. Everything here was checked against the code.

**Start here:** the repo is `F:\Projects\GameTheory`. One command runs
everything: `python driver.py` (app), `python driver.py --check` (all nine
checks), `python driver.py --bench`. Green as of the last commit: 483 backend tests, 49 frontend, nine checks.

**There is no outstanding implementation work.** Everything SPEC asks for is
built, and the three open questions from the last pass are closed: the
half-built `subscribe_agent` channel was retired, deaths by cause is
measured and shown, and ageing speed is a dial in the new-world dialog
defaulting to a measured 3.0. What follows is a list of false leads, so
nobody re-reports them, and two things only Alex can do.

---

## 1. Things that look like gaps and are not

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

## 2. Still needs Alex, not Claude

- **The GitHub repo.** 30 commits are waiting with no remote.
  `winget install GitHub.cli ; gh auth login ;
  gh repo create AlexBoyev/GameTheory --private --source=. --push`
- **Delete `F:\Projects\TheoryGames`.** An empty husk left by the rename; a
  session's working directory was pinned inside it, which is why git reported
  "not a repository" from there. Start Claude Code in `F:\Projects\GameTheory`.

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
