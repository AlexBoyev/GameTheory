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
| `pytest` | 419 passed |
| `tsc -b`, `eslint` | clean |
| `vitest` | 34 passed |
| `playwright` | 14 passed, repeated runs |
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

8. **A preset was a one-way door.** `POST /sim/reset` with no config
   rebuilds from the *current* config, which is reasonable on its own ("same
   world, new seed") but meant that choosing the Axelrod preset once left
   `tournament_mode` on with no way to clear it from the UI - and a
   tournament world runs no decision system, so it looks exactly like a
   broken simulation. `GET /sim/defaults` now says what "default" means and
   the New World dialog builds on that rather than on the running world.

   Found by a browser test failing for the wrong reason: it reported no
   decision traces anywhere, which was true, because the world it inherited
   had no decision system.

## Findings, by priority

### ~~P1 - the declared utility-AI design is not the implemented one~~ (partly fixed)

SPEC 7.4 describes "considerations + response curves"; every skill instead
computed `utility()` with hand-rolled arithmetic, and `apply_curve` was
unit-tested while production code never called it.

A skill may now declare `considerations()` - named inputs with a weight and a
curve - which the base class sums. The nine survival skills are converted;
the rest still override `utility()` and score exactly as before.

**The payoff is the decision trace.** It said `Sleep 0.194`; it now says
`Sleep 0.194 - tired +0.12, it is night +0.07`, and the inspector shows those
lines under each option. That is the difference between watching a simulation
and reading one, which was the original complaint that started the UI work.

Three things worth recording about doing it:

1. **The conversion had to be proved, not assumed.** 1,240 utility values
   were captured before the change for comparison - which showed 356 drifting
   and, more usefully, drifting for skills that had not been touched. That
   ruled out transcription error and pointed at the world trajectory: one
   last-bit difference changes a softmax draw, which changes every subsequent
   decision. Whole-world comparison is therefore useless for this; the
   verification that works is writing each original formula out again in a
   test and comparing per-skill. Those tests exist.
2. **It found a real bug.** `apply_curve` clamps its input to `[0, 1]`, so
   three skills whose value could reach 1.4 (`Gather`'s greed term, wood
   gathering's loyalty term, `Flee`'s timidity term) were silently scoring
   1.0. The magnitude belongs in the weight, which is not clamped.
3. **An explanation whose parts do not add up is worse than none.** The first
   version listed only a skill's own considerations, so `BuildShelter` showed
   0.90 against a single input of 0.65 - the missing 0.25 being the commitment
   bonus the brain adds. The trace now names those bonuses too, and a test
   asserts the parts sum to the score.

All 31 skills are now converted, and nothing overrides `utility()` any
more, so the inspector can explain every option it shows. Two thirds of them
turned out to be a single product of factors, which reads better as one
honestly named input ("greedy and dishonest 0.42") than as a forced
decomposition; three expanded exactly into two real inputs, and those were
worth splitting - `JoinTribe`'s standing wish to belong is a different thing
from how unsafe the agent feels this second.

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

### ~~P2 - `Raid` was a feature that never happened~~ (fixed)

Found by finishing the considerations conversion and then asking a running
world which skills its agents actually explain. In 6,000 ticks `Raid` never
once entered a decision trace. Its three preconditions were not the problem -
measuring them separately showed a war on, a stocked enemy and a raider 3.9
units from the camp all coinciding on six sampled ticks. The problem was the
score: a raid was wanted on temperament alone (`aggression * loyalty`, median
0.056) and never outscored picking berries (~0.33), so the softmax never drew
it. The one thing a raid is *for* - the enemy's full store - was not an input.

It is now, as "their store is worth taking", and raids happen about once per
1,500 ticks, which is rare without being dead. The food really moves: "Ada-ka
raided Clifffolk and took 4.0 food".

The general lesson, for the third time in this project: a skill can be
registered, tested, reachable and still never fire. Only a running world
tells you, and the decision trace is the instrument.

### ~~P2 - no coup could ever succeed, and no tribe could ever sign a pact~~ (fixed)

Two more found the same way as `Raid`, by asking a running world what its
agents actually do rather than what the code says they can.

**Coups.** 35 attempts in 12,000 ticks, none successful, and no deposed
leader ever reached `TribeRole.ELDER` - the role only that path assigns. The
cause was `COUP_MARGIN = 0.25`: `legitimacy` is a product of three bounded
factors, so sampling every tribe every 200 ticks the best-placed rival beat
the sitting leader by at most **+0.208**, median -0.047. The margin sat
outside the entire observed distribution. `test_tribes.py` had a passing
coup test the whole time, because it hand-built the scenario and asserted it
was winnable - a scenario the world cannot produce. The margin is now 0.05,
measured rather than guessed: across five seeds, 7 coups of 190 attempts.

**Tribe pacts.** SPEC section 6 specifies alliances "between agents or
tribes". The agent half worked. The tribe half had a `Tribe.allied_with`
field, a DTO field, snapshot serialisation, a world query, and
`DeclareWar` breaking a pact on sight - and no code anywhere that could add
one. The only writes were `discard`. `OfferAlliance` now fills it: a leader
courts the tribe whose members their own people think best of, and a
belligerent leader on the other side refuses. Pacts form in every seed.

That makes three dead features in one sweep, all of which had tests. A unit
test proves a path works when you set the stage for it; only a running world
tells you the stage ever gets set.

### ~~P3 - two tribes could be drawn in the same colour~~ (fixed)

`tribe_name` was made unique after three tribes came out called Holtclan.
The colour kept indexing an eight-entry palette with `id % 8`, so Clifffolk
and Cliffkin were drawn identically - and colour, not name, is what the
scene puts on a bean and a territory ring. Sixteen tribes alive at once is
ordinary, so every long run had collisions. `tribe_colour` now keeps the hue
of the name's stem and deepens it per naming cycle: Cliffkin reads as a
darker Clifffolk, 32 ids give 32 distinct colours, and none is near black.

### The sweep is now a test

Three dead features in one session is a pattern, not bad luck, so
`tests/ai/test_reachability.py` keeps the instrument: it runs 6,000 ticks of
a full society and asserts that every registered skill is wanted by somebody
at some point, that tribes form, fight, settle and sign, and that a
challenger somewhere reaches a position from which a coup could be won. It
costs about 38 seconds, which is roughly a fifth of the suite, and it is the
only test in the repo that could have caught any of the three.

Two things about it are easy to get wrong and are written down in the file:
read each skill's score rather than the decision trace, which keeps only an
agent's top three and so hides a skill that is always wanted and never best;
and sample every tick, because checking every 25th missed `OfferPeace` in a
seed that demonstrably made peace - the war started and ended in between.

### ~~P1 - three of the four tables were never written to~~ (fixed)

The fourth instance of the same failure, and the largest. SPEC sections 10
and 11 promise runs, metrics, snapshots and a capped event log in SQLite.
Only snapshots were ever written. `Repository` had `create_run`,
`add_metrics`, `metrics_since`, `add_events` and `recent_events`; the tables
were created on every startup; `EventRecord` was never constructed anywhere;
and `MetricsService.__init__` took a `Repository`, stored it, and never
called it. Both routers carried a comment saying the SQLite path would
"arrive in Phase 4" - it never arrived in any phase.

So charts and the feed lived in a ring buffer and died with the process, and
a run longer than 2,000 samples silently lost its own beginning.

`RunArchive` (ADR 0006) now owns the run, writes to it on its own thread
behind a bounded queue, and reads it back; `MetricsService.series` and
`GET /events` stitch memory and disk so the caller sees one series. The
integration test asserts against the *running app* that rows land, because
the unit tests for a correct, unreferenced collaborator would all have
passed on the day nothing called it - which is precisely what happened here
for six phases.

### ~~P2 - two settings that did nothing and one that lied~~ (fixed)

Sweeping every declared name for readers - the sixth and seventh instances
of the pattern, found mechanically rather than by luck.

- `llm_circuit_failures` and `llm_circuit_cooldown_s` were read by nothing.
  `LLMScheduler` defaulted its breaker to `CircuitBreaker(threshold=3,
  cooldown_s=60.0)`, which is *exactly* the settings defaults, so editing
  either in `.env` changed nothing and the behaviour still looked right.
  Duplicating a default is how a missing wire hides. The gateway now builds
  the breaker from settings, and the scheduler's fallback no longer repeats
  the numbers.
- `sim_tick_rate` described itself as "Ticks per second at 1x speed" and was
  read nowhere. The engine derives the pace from `1.0 / config.dt`, which is
  the better design - it makes 1x mean "one sim-second per wall-second" by
  construction - but it left a setting in `.env.example` that silently did
  nothing. Removed, and `sim_dt` now documents that it sets the pace.

Two near-misses worth recording so nobody re-reports them: `strategy_mix` is
read through `normalised_strategy_mix`, and every `balance` constant and
entity field is used.

### ~~P2 - the socket advertised a channel it never served~~ (fixed)

Found by sweeping the *protocol* rather than the code: every path in the
OpenAPI schema against the frontend's calls, every websocket envelope type
against its handlers. Every REST endpoint is called. The socket was not so
clean.

SPEC section 8 listed `agent_detail` (S->C, "for the subscribed agent only")
and `subscribe_agent` (C->S). The server accepted the subscription, stored
it on the connection as `subscribed_agent`, and replied `{pending: true}` -
and **nothing ever read that field**. A client that implemented the
documented protocol subscribed and then waited forever. The frontend never
noticed because it polls `GET /api/agents/{id}` at 2 Hz instead.

Retired rather than finished, which was the closer call of the two. The
polling is justified on its own terms - one agent is inspected at a time, so
a small request beats pushing detail to every connected client at 20 Hz -
and finishing the channel would have meant adding a throttle and a second
path to the same data for a latency improvement nobody asked for. Both
messages are still recognised and answered with an error naming the REST
route, because a client told "ok" by a server that will never follow up is
worse off than one told where to look. `MessageType.AGENT_DETAIL` is gone:
if the type exists, somebody will eventually wait for it.

### ~~P2 - evolution had nothing to select on~~ (fixed)

The simulation's premise is inherited, mutating strategies under selection.
Selection needs agents to die of something other than bad luck, and they
did not: `balance.AGE_YEARS_PER_DAY = 1.0` was annotated "ages fast on
purpose: a lifetime should be watchable in minutes", and the arithmetic says
otherwise - 2,400 ticks a year, so the *oldest* agent the world spawns needs
52,800 ticks to reach `MAX_AGE` and a typical one about 91,000. At 1x that
is hours. Across 27,000 measured ticks nobody died of old age once; the
population simply grew.

The pace is now `WorldConfig.age_years_per_day`, defaulting to 3.0, with a
slider in the new-world dialog - Alex asked for it to be configurable at the
start, which is right: it is the dial that decides what kind of place the
island is.

Three was chosen by sweeping 30,000-tick runs rather than by taste:

| years/day | alive | births | deaths | of old age | mean age |
| --- | --- | --- | --- | --- | --- |
| 1.0 | 195 | 83 | 8 | 0 | 28 |
| 2.0 | 192 | 81 | 9 | 3 | 38 |
| **3.0** | **118** | 40 | 42 | **40** | 50 |
| 4.0 | 57 | 28 | 91 | 89 | 49 |
| 6.0 | 17 | 17 | 120 | 120 | 52 |

Three is the knee: births and deaths balance, and most deaths are finally
old age. The curve is sharp just above it, which the slider's hint says, and
the whole social machinery still runs at the new default - the reachability
suite still finds tribes founded, a war declared and settled, pacts signed
and a coup won.

### ~~P0 - high speeds froze the backend outright~~ (fixed)

Reported from use, not found by a sweep: "speed it up to x25/x50, backend
disconnected". It reproduced exactly, and it was worse than a disconnect -
the engine wedged. Measured mid-failure: tick frozen at 93,298 for over a
minute with 411 agents, `status: running`, the process burning a full core,
the websocket resetting through the Vite proxy, the UI stuck, and metrics
sampling stopped dead at 22 samples in 93,000 ticks.

`_run_slice` bounded catch-up by tick *count* (`MAX_TICKS_PER_SLICE`, 4,096)
and not by time, except at MAX speed which had a 12 ms budget. A count is
not a bound on time: how long 4,096 ticks take depends on the population,
and at 400 agents it is over a minute - all of it holding the world lock, so
no frame is published, no command is read (Pause included) and no metrics
are sampled. Worse, `_tick_debt` accrued in real time regardless of whether
the engine could ever catch up, so falling behind guaranteed a spiral:
longer slice, more debt, longer slice.

Now every speed gets the same wall-clock budget, and the debt is capped at
`MAX_DEBT_TICKS`. A world that cannot hit its requested speed simply runs
slower, which the tps readout already shows honestly. Measured after, 400
agents at 50x: a steady ~20 tps, `/api/sim/state` answering in 5-50 ms,
metrics sampling every 100 ticks, and the browser at 134 fps with the event
log open. Before: 0 tps and nothing answering.

The old test for this asserted `<= MAX_TICKS_PER_SLICE` and passed
throughout, which is the lesson worth keeping: a bound of 4,096 ticks was
loose enough to be no bound at all. There is now a test that the batch stops
when its *time* is up.

### P2 - the engine cannot reach 25x with a large island, and now says so

Measured with the project's own bench, pure engine, 400 ticks:

| agents | ticks/s | fastest honest speed |
| --- | --- | --- |
| 100 | 350 | ~35x |
| 150 | 233 | ~23x |
| 300 | 98 | ~10x |
| 500 | 54 | ~5x |

So "25x with 400 agents" was never deliverable - it is three to five times
over capacity. Before the pacing fix above that overload froze the backend;
now it simply runs slower, and the control bar says which: the tps readout
turns amber and reads `25 tps - 3x` when the engine is below three quarters
of what the speed button asked for. A number you can see beats a promise
the machine cannot keep.

**Two micro-optimisations measured and rejected.** `query_radius` really is
the hot spot - 33% of a tick at 300 agents, 820 calls per tick - but not for
the reason the shape of the code suggests:

- *Row-major buckets* (`{row: {column: [...]}}` instead of a `(column, row)`
  tuple key, so the row lookup hoists out of the column loop and empty rows
  skip their span). No change: 38.5ms against 39.1ms, inside noise, and
  `dict.get` calls went *up* 8%, because a row probe is added per row while
  only a tuple allocation is removed.
- *Fusing the self-exclusion* into the scan so `neighbours` stops building a
  second list. Also no change - 78.2 tps against a 79.9 tps baseline whose
  own spread was 76-84 - because it puts a branch in the innermost loop,
  which runs per candidate rather than per call.

Both were reverted. The cost is the number of candidate points scanned, and
that is set by density and by how many queries the scoring pass makes, not
by key construction or an extra list pass. `nearest_resource`'s docstring
records a third attempt (per-tick memoisation, ~4%, reverted in ADR 0005).
Anything better than a few percent here is structural - fewer decisions per
tick, or scoring vectorised across agents - not a tweak.

### ~~P1 - the socket could be open and dead, and the UI froze forever~~ (fixed)

Found by refusing to accept a flaky test twice. One e2e case - "connects to
the world socket and receives frames" - failed intermittently, passed in
isolation, and passed again on a clean stack. The first time I put it down
to ordering and moved on, which was wrong: it was reproducible by running
the two specs in sequence, and the diagnostic was unambiguous. The backend
advanced from tick 768 to 867 while the page's tick stayed at 757 for eight
seconds, with the status indicator still reading "live".

Vite proxies the websocket in development. When the backend side of that
proxy resets - `ECONNRESET`, plainly in its log - the browser side is left
*open*. No `close` event fires, so the client's reconnection, which hangs
off `onclose`, never runs. REST polling keeps working on its own path, so
speed and status keep updating while the world sits frozen on its last
frame. It looks exactly like a crashed backend and is not one; this is very
likely what was reported as "backend disconnected" at high speed.

The client now watches for silence rather than waiting to be told. Frames
arrive about twenty times a second whether the world runs or is paused, so
six seconds without a message means the pipe is gone: the watchdog closes
the socket, which fires `onclose`, which is the one path that knows how to
retry. Two tests cover it - a silent socket is closed and reconnected, a
chatty one is left alone indefinitely - and the e2e suite went from
intermittent to 16/16 twice over.

Worth keeping: *an intermittent test is a bug report with a bad summary.*
This one was dismissed once as ordering flakiness and was a genuine defect
that would have frozen a real session with no error anywhere.

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
