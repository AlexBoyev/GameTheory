# What is left, in the order I would do it

Written 2026-11-23 so a fresh session can pick up without re-deriving the
state. `docs/REVIEW.md` has the reasoning behind each finding; this is just
the queue. Everything below was checked against the code, not guessed.

**Start here:** the repo is `F:\Projects\GameTheory`. One command runs
everything: `python driver.py` (app), `python driver.py --check` (all nine
checks), `python driver.py --bench`. The suite is green as of commit
`f41a6d4`: 475 backend tests, 41 frontend, nine checks passing.

---

## 1. The two charts SPEC 9.4 asks for and the UI does not have

`frontend/src/ui/ChartsPanel.tsx` draws Population, Strategy shares,
Cooperation by game, and Food inequality & trust. SPEC section 9.4 also lists:

- **Average payoff per strategy.** `payoff_by_strategy` is computed on every
  sample from `ledger.average_payoffs()`, served in `MetricPointDTO`, and
  present in `frontend/src/api/generated.ts`. Nothing renders it. This is a
  frontend-only change: another `<Chart>` with one series per strategy,
  coloured the same way Strategy shares already colours them.
- **Betrayals and alliances over time.** Both counts are in `point.extra`
  (`betrayals`, `alliances`, and `lies_told` / `lies_caught` are there too).
  They are cumulative counters, so either plot them cumulatively or difference
  consecutive samples - decide which reads better and say why in a comment.

Watch for: `extra` is `dict[str, float]` over the wire. The existing charts
show the pattern for pulling a series out of `points`.

## 2. Deaths by cause (SPEC section 10)

SPEC lists "deaths by cause" among the metrics. `MetricPoint.deaths` is a
bare count. The cause exists - `EventType.DEATH` carries it in `event.data`,
and the README advertises "deaths with causes" - but nothing aggregates it
into the metrics.

Approach: count causes on the world (a `Counter` beside `world.deaths`, reset
with the world) rather than by scanning events, which the metrics sampler
cannot see. Then surface it in `extra` as `deaths_starvation` and so on, or
as its own dict field on `MetricPoint` if it deserves one.

Worth knowing before you tune anything: **almost nobody dies.** A 10,000-tick
run on the default seed produced 29 births against 4 deaths, population
climbing from 120 to 145 toward the cap. A deaths-by-cause chart of a world
where nothing dies is honest but dull, so this may be worth pairing with a
look at whether the survival pressure is where it should be. That is a design
question for Alex, not a bug.

## 3. Traits radar (SPEC section 9.4) - cosmetic

The Inspector draws traits as bars (`Inspector.tsx`, the `detail.traits` map).
SPEC says radar. Small, self-contained, and purely visual; do it when the
more substantial items are done.

## 4. Things that look like gaps and are not

Do not "fix" these; each was checked.

- `ResourceKind.STONE` spawns and is consumed by nothing. Deliberate scenery;
  the help overlay says so rather than promising a use.
- `EventType.ENCOUNTER` never reaches the feed. It is the *memory* entry for
  an encounter; the feed always gets `BETRAYAL`/`COOPERATION`/`COMBAT`/
  `DEFECTION` instead.
- `EventType.LEADER_CHANGED` fires only when a leader dies. A won coup emits
  `COUP` with `succeeded: true`, which is reasonable.
- `AgentState.MOVE` is plan-only; `AgentState.TRADE` does appear, it is just
  too brief to catch with coarse sampling.
- `llm_agents` defaults to 4, so default runs are not bit-reproducible. This
  is deliberate and documented in ADR 0004 and `docs/REVIEW.md`.

## 5. Still needs Alex, not Claude

- **The GitHub repo.** 21 commits are waiting with no remote.
  `winget install GitHub.cli ; gh auth login ;
  gh repo create AlexBoyev/GameTheory --private --source=. --push`
- **Delete `F:\Projects\TheoryGames`.** It is an empty husk left by the
  rename; the previous session's working directory was pinned inside it,
  which is why git reported "not a repository" from there. Start Claude Code
  in `F:\Projects\GameTheory`.

---

## How to look for the next real bug

Four features in this project were registered, typed, unit-tested, and
connected to nothing: `Raid`, a winnable coup, tribe pacts, and three of the
four database tables. None of them were found by reading code or by running
the suite. All four were found by running a world and asking what actually
happened.

`tests/ai/test_reachability.py` now keeps that instrument pointed at the
skills. The same question is worth asking of anything else that is declared
once and used elsewhere: every enum member, every settings field, every
repository method, every DTO field the frontend never reads. The sweep in
that file's `Run` class is the template - and read its docstring first, since
both of its sharp edges (read scores not the trace; sample every tick) cost
me a wrong answer before they were written down.
