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
| `mypy app` (strict) | clean, 130 files |
| `lint-imports` | 7 contracts, 0 broken |
| `pytest` | 350 passed |
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

### P1 - every decision scores all 31 skills

`UtilityBrain._score_all` runs `check()` and `utility()` for every registered
skill on every decision: 44% of runtime at 500 agents, and the reason the
neighbour search is the hottest function in the profile.

Most of those skills are ruled out by the agent's situation before any
arithmetic (tribe skills for a tribeless agent, combat for a pacifist, every
social skill when nobody is nearby). A cheap pre-filter - by category against
a handful of agent facts - is the real performance headroom.

**Not fixed here**: see ADR 0005 for the per-tick memo that was tried,
measured at ~4% (inside the noise), found *unsafe* (skills mutate the world
during a tick, so a cached answer goes stale silently) and reverted. The
structural fix is the one worth making, and it belongs in a phase of its own.

### P2 - seven files exceed the 300-line guideline

| File | Lines |
| --- | --- |
| `services/simulation_service.py` | 553 |
| `ai/skills/manipulation.py` | 528 |
| `ai/skills/social.py` | 493 |
| `sim/engine.py` | 436 |
| `services/serialisation.py` | 366 |
| `ai/gametheory/resolver.py` | 350 |
| `ai/skills/sustenance.py` | 325 |

`tribe.py` was the outlier at 652 and has been split. The rest divide into two
kinds, and I would treat them differently:

- **Collections of independent things** (`manipulation`, `social`,
  `sustenance`): splitting these is safe and mechanical, exactly as done for
  `tribe.py`. Worth doing, low risk, no urgency - a 500-line file of
  independent skills reads nothing like a 500-line class.
- **One responsibility that is genuinely large** (`simulation_service`,
  `engine`, `serialisation`, `resolver`): splitting these would split *one*
  responsibility across files and make the thing harder to follow, not
  easier. `simulation_service` is the clearest candidate for real work - the
  broadcast pump could become its own collaborator - but that is a refactor
  with a behavioural blast radius, not a tidy-up.

### P2 - `mypy` does not cover `tests/`

`driver.py --check` runs `mypy app`. Pointing it at `tests/` reports 84 errors
(mostly missing annotations on fixtures and deliberate `object` parameters in
helpers). The tests are the least type-safe code in the repo, which is
backwards: a mistyped test is a test that passes for the wrong reason.

**Not fixed here**: 84 errors is a focused session of its own, and fixing them
badly (blanket `Any`) would be worse than leaving them.

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

### P3 - `FrozenPacer` is an unused test seam

`services/pacer.py` provides a deterministic pacer "for tests", and no test
uses it; the engine tests drive the real clock with bounded polling instead.
Either adopt it (engine tests would get faster and fully deterministic) or
delete it. I left it because it is correct, documented, and cheap - but it is
currently a promise nothing keeps.

### P3 - constant tables are mutable dicts

`TOOLS`, `DESCRIPTIONS`, `DEFAULT_PAYOFFS` are module-level `dict`s used as
constants. Nothing mutates them, and `Mapping` annotations would make that a
guarantee rather than a convention.

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
