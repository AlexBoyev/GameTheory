# Senior review - Game Theory

- **Date:** 2026-11-23
- **Scope:** the whole repo, against `CLAUDE.md` and `docs/SPEC.md`
- **Method:** every linter, type check and test suite; machine-checked
  architecture contracts; a dead-code scan; repeated runs of the
  timing-sensitive tests; a real-browser pass; and a profile at 500 agents

## Verdict

The architecture holds. The layering, determinism and cost rules are not
merely followed but *machine-checked*. What this review actually found was
four settings that were declared, documented, tested as functions and read by
nothing - and every time I assumed something about the running system instead
of measuring it, I was wrong. Those two patterns are the main thing this
document records.

| Gate | Result |
| --- | --- |
| `ruff format`, `ruff check` | clean |
| `mypy app tests` (strict) | clean, 173 files |
| `lint-imports` | 7 contracts, 0 broken |
| `pytest` | 401 passed |
| `tsc -b`, `eslint` | clean |
| `vitest` | 34 passed |
| `playwright` | 13 passed, repeated runs |
| `vite build` | clean |

### The hard rules

| Rule | Evidence |
| --- | --- |
| No paid or cloud AI, no keys, no billing | Nothing in `app/`, `tests/` or `frontend/src` matches any provider name or key pattern |
| No runtime network calls except Ollama | The only non-local URL in the codebase is the Ollama default; everything else is a docs link in a comment |
| `sim/` is pure and deterministic | Contract forbids `time`, `datetime`, `random`, `secrets`, `uuid` and every upper layer; determinism test green |
| `ai/` reads `sim/`, never the reverse | Contract; and it is why `tribe_identity` moved into `sim/` this phase |
| Constructor DI, no module-level mutable state | Only module-level dicts are constant lookup tables (payoffs, preset descriptions, the god-tool registry) |

## Fixed in this pass

1. **Four unused symbols deleted.** `believed_reputation` (superseded by
   `effective_opinion`), `not_implemented_yet` (nothing answers 501 any more),
   `make_generator` (superseded by `derive_generator`), and the
   `Consideration` dataclass (see finding 1).
2. **`tribe.py` split**, 652 lines into four files by subject - membership,
   storage, politics, and the dials they share. All 31 skills still discovered.
3. **Two overlay toggles that had been promising "Phase 6 data" since Phase 3
   now work**: an activity heatmap accumulated in the browser from the frames
   already arriving, and name tags for the agents nearest the camera.
4. **The screenshot button no longer costs every frame.** It was implemented
   with `preserveDrawingBuffer: true`, which makes the driver keep a copy of
   every frame - headless Chrome reports it as "GPU stall due to ReadPixels".
   An in-scene `Screenshotter` now re-renders and reads the buffer only when
   asked, so the cost lands on the one frame you wanted.
5. **The e2e suite actually tests the app.** It contained only the Phase 1
   shell tests, with a comment promising the Phase 3 control-bar tests that
   never arrived. There are now 12 tests covering play/pause, speed presets,
   step, reset, preset builds, panel toggles, a god tool and a snapshot save.
   Two defects surfaced immediately:
   - Adding the minimap broke the existing smoke test: a second `canvas` made
     `locator('canvas')` ambiguous under strict mode. Nobody noticed because
     the suite could not run - the installed browser predated the installed
     Playwright.
   - The tests shared one backend and silently depended on the state the
     previous test left. Each now puts the engine in a known state first.
6. **Stale documentation corrected**: `playwright.config.ts` claimed the
   backend must be on `:8000`, which Apache holds on this machine.

7. **Tournament mode was the fourth "declared but wired to nothing".**
   `WorldConfig.tournament_mode` had a field, a description, a SPEC section
   and a preset - and nothing read it, so the Axelrod preset quietly built a
   normal island with a flat strategy mix. It is now a real pipeline
   (`Perception + TournamentSystem`, survival off), a ring arena, a
   `GET /api/sim/tournament` report and a UI panel that appears only while a
   tournament is running. 21 tests, including one that asserts the simulation
   reproduces Axelrod's actual finding.

   The other three were `trait_bias`, `initial_tribes` (both Phase 6) and
   `SchedulerLimits.interval_for_speed` (Phase 5). The pattern is worth
   naming: a field with a docstring, a test of the *function* and no caller
   reads as finished work in every review that does not run it.

## Findings, by priority

### P1 - the declared utility-AI design is not the implemented one

SPEC 7.4 and `utility_brain.py` describe "considerations + response curves".
In practice all 32 skills compute `utility()` with hand-rolled arithmetic;
`apply_curve` exists and is unit-tested but **production code never calls
it**, and the `Consideration` wrapper was unreferenced scaffolding (now
removed).

This is not a bug - the skills work and are individually readable - but the
SPEC describes a composable, inspectable scoring mechanism and what exists is
32 bespoke formulas. Adopting it would also make the decision trace far more
useful (it could name the *inputs*, not just the skill).

**Not fixed here** because rewriting 32 utility functions is a design change,
not a cleanup. If it is taken on: do one skill first, prove the trace improves,
then convert the rest.

### ~~P1 - every decision scores all 31 skills~~ (partly fixed)

`UtilityBrain._score_all` ran `check()` and `utility()` for every registered
skill on every decision: 44% of runtime at 500 agents. Most of those skills
are ruled out by the agent's situation before any arithmetic - a tribeless
agent alone in a field cannot gossip, raid, store food or declare war.

Each skill now declares the cheap facts it cannot run without
(`Requirement.NEARBY_AGENTS`, `IN_TRIBE`, `TRIBELESS`, `TRIBE_LEADER`), the
brain computes them once per decision from state it already has, and the
impossible ones never get a call. The same gate filters the skills offered to
the LLM, which previously ran all 31 `check()`s to build a prompt.

**It is safe because it is machine-checked, not because it looks right.** The
rule is that an unmet requirement must *imply* a failing `check()` - a
requirement is a cheap pre-test of something `check()` already enforces, never
a new condition. `test_an_unmet_requirement_implies_a_failing_check` asserts
exactly that for every agent and every annotated skill in a world that has run
240 ticks, because getting it wrong would silently disable a skill with no
error anywhere. That test is the reason this landed and the per-tick memo (ADR
0005) did not.

**Measured, A/B, median of three runs:**

| | skipped scoring | with gate | without |
| --- | --- | --- | --- |
| 100 agents | 24% | 374 ticks/s | 346 |
| 500 agents | 23% | 56 ticks/s | 54 |

So about a quarter of all skill scoring disappears, for 4-8% of wall clock.
The gap is itself the finding: the skills being skipped are the ones with
*cheap* checks, while the expensive part of `_score_all` is the survival
skills' spatial queries - and those can never be skipped, because an agent
always needs to eat. What remains is `nearest_resource`, which is exactly what
the reverted memo targeted. A safe fix there would need the world to tell the
cache when it changes, which is a bigger change than either attempt.

### ~~P2 - seven files exceed the 300-line guideline~~ (largely fixed)

`tribe.py` (652) was the outlier and is now four files by subject.
`manipulation.py` (533) split into `deception.py` and `coercion.py`;
`social.py` (498) gave up reproduction to `heredity.py` and its targeting
helpers to `targeting.py` - that last one a structural fix rather than a line
count, since combat, manipulation and the tribe skills were all importing
`social` purely to reach `nearby_agents`.

`simulation_service.py` was the remaining real one at 584, and the broadcast
pump is now its own collaborator (`services/broadcast.py`). Two threads meet
in that class and nothing else, which is why it deserved to be one: the engine
thread only ever queues, the event loop only ever drains and fans out. What
stayed behind are the *policies* that happen to run once per frame - metrics
sampling and the LLM speed interval - handed in as a hook, because neither is
transport.

The extraction paid for itself immediately: 21 tests now cover behaviours that
were previously reachable only through the HTTP API and a running simulation
(dropping the stale frame, resource deltas, surviving a subscriber that
throws, speech getting its own channel).

What is left over 300 lines is either one genuinely large responsibility
(`engine.py` 436, `serialisation.py` 366, `resolver.py` 350, and
`simulation_service.py` still 459 - owning the engine thread, commands,
queries, god tools and snapshots) or 5-25 lines over, where splitting is
churn. I would leave all of them.

### ~~P2 - `mypy` does not cover `tests/`~~ (fixed)

`driver.py --check` ran `mypy app`, and pointing it at `tests/` reported 84
errors. The tests were the least type-safe code in the repo, which is
backwards: a mistyped test is a test that passes for the wrong reason.

It turned out to be far smaller than the count suggested. **74 of the errors
came from one wrong annotation** - a helper in `test_encounters.py` declared
`-> tuple[object, object]` when it returns two agents, so every attribute
access on its result was an error. The rest were my own `dict[str, object]`
on JSON responses (JSON is untyped, so `Any` is the honest annotation and
`object` just forces a cast at every use), one missing annotation, and ten
`type: ignore` comments that no longer suppressed anything.

`mypy app tests` is now clean under the same strict settings and runs in the
gate, so it stays that way.

### ~~P2 - the event feed evicts rare events under load~~ (fixed)

`RECENT_EVENTS = 500`, and a busy world generates mostly gossip. Twice during
this build I queried the feed for something I had just caused - a god action,
a speech line - and got nothing, each time concluding briefly that the feature
was broken. It was not; the event had been pushed out.

Fixed by `services/event_store.py`, which retains the same events two ways: a
chronological buffer for reading top to bottom, and a per-type buffer so the
last 40 of each *kind* survive however much noise follows. Filtering now reads
the per-type buffer, because filtering the chronological one filters rows that
have already gone and quietly returns nothing.

Demonstrated in a live world: after overflowing the 500-event cap, **zero** god
actions remained in the chronological feed and both were still returned by
`GET /api/events?type=god_action`. Retention stays bounded at
`per_type x number of types`.

### ~~P3 - `FrozenPacer` is an unused test seam~~ (fixed)

`services/pacer.py` provided a deterministic pacer "for tests" and no test
used it. Rather than delete it, it turned out to enable a test that was
missing: **nothing checked the pacing arithmetic at all.** With a real clock
the question "does 2x earn twice the ticks" is unanswerable; with a frozen one
it is five assertions.

So there are now tests that one real second at 1x earns exactly ten ticks
(dt is 0.1), that speed multiplies that, that fractional ticks are *banked*
rather than lost (at 20 Hz each slice earns half a tick at 1x), that a long
stall cannot run an unbounded catch-up batch, and that a clock going backwards
earns nothing. An unused seam became coverage of a contract nothing was
testing.

### ~~P3 - constant tables are mutable dicts~~ (fixed)

`TOOLS`, `DESCRIPTIONS` and `DEFAULT_PAYOFFS` are now annotated `Mapping`, so
"nothing mutates them" is a guarantee rather than a convention.

### P3 - `llm_agents` defaults to 4, so default runs are not bit-reproducible

Deliberate and documented (ADR 0004, `WorldConfig.llm_agents`): the
deliberative layer is visible out of the box, and `llm_agents: 0` restores
bit-for-bit reproducibility. Recorded here only so that nobody rediscovers it
as a bug - the determinism *test* runs with the LLM off, as CLAUDE.md requires.

## What I got wrong while building this, and what it cost

Worth keeping, because the pattern repeats:

| Assumption | What was true |
| --- | --- |
| "The event-feed render is what makes it 1 fps" | My measurement harness never composited, so Chrome throttled `requestAnimationFrame`. Every fps number I had was an artifact. |
| "No shelters are being built, so the skill must be wrong" | The cooldown started when a skill *began*, so any skill longer than the review interval could never finish. |
| "Caching the repeated neighbour searches will be a clear win" | ~4%, inside the noise, and unsafe. Reverted. |
| "The high-speed policy works, it is tested" | Nothing called it. The setting existed, the UI displayed it, and it did nothing. |
| "Tournament mode is done, there is a preset for it" | Same again: a config field, a SPEC section and a preset, read by nothing. |

Three of those four were found by probing a *running* world rather than by
reading code or adding unit tests. The unit tests were green throughout.
